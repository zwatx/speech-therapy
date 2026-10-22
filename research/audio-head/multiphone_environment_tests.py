import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import wave

import multiphone_environment_challenge as subject


class EnvironmentTests(unittest.TestCase):
    def rows(self):
        return [dict(filename=f'1-{index}-{letter}.wav', src_file=str(index),
                     category=category, fold='1', esc10='True')
                for category in subject.CATEGORIES
                for index in range(3) for letter in ('A','B')]

    def test_selection_is_sorted_distinct_and_esc10_fold1_only(self):
        rows = self.rows()
        # Real metadata names are unique across categories.
        for row in rows: row['filename'] = row['category']+'-'+row['filename']
        extra = dict(rows[0], filename='000.wav', esc10='False')
        wrong_fold = dict(rows[0], filename='001.wav', fold='2')
        selected = subject.select_rows(list(reversed(rows))+[extra,wrong_fold])
        self.assertEqual(len(selected), 12)
        for category in subject.CATEGORIES:
            group = [row for row in selected if row['category'] == category]
            self.assertEqual([row['src_file'] for row in group], ['0','1'])
            self.assertTrue(all(row['filename'].endswith('-A.wav') for row in group))

    def test_missing_category_or_duplicate_filename_fails(self):
        rows = self.rows()
        with self.assertRaises(ValueError): subject.select_rows(rows)
        with self.assertRaises(ValueError): subject.select_rows([])

    def wav(self, path, rate=44100, frames=220500):
        with wave.open(str(path),'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
            stream.writeframes(b'\x01\x00'*frames)

    def test_real_conversion_keeps_whole_duration_and_refuses_overwrite(self):
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg is None: self.skipTest('ffmpeg unavailable')
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root)/'source.wav', Path(root)/'target.wav'
            self.wav(source)
            command = subject.convert(source,target,ffmpeg)
            subject.check_wave(target,16000)
            self.assertNotIn('-af', command)
            with self.assertRaises(ValueError): subject.convert(source,target,ffmpeg)

    def test_bad_format_and_conversion_failure_are_errors(self):
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root)/'source.wav', Path(root)/'target.wav'
            self.wav(source,16000,80000)
            with self.assertRaises(ValueError): subject.convert(source,target,'unused')
            self.wav(source)
            with patch.object(subject.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['ffmpeg'])):
                with self.assertRaises(subprocess.CalledProcessError): subject.convert(source,target,'ffmpeg')
            self.assertFalse(target.exists())


if __name__ == '__main__': unittest.main()
