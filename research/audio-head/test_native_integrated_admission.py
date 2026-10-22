"""Actual ct9 type/protobuf metadata regression checks; never instantiate a model."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-hidden-integrated-admission-20261015'))
import admit_saved as subject


def spec_fixture():
    from coremltools.proto import Model_pb2, MIL_pb2 as mil, FeatureTypes_pb2 as features
    model = Model_pb2.Model()
    model.specificationVersion = 8
    function = model.mlProgram.functions['main']
    function.opset = 'CoreML7'
    block = function.block_specializations['CoreML7']

    def typed(value, shape, dtype):
        tensor = value.tensorType
        tensor.dataType, tensor.rank = dtype, len(shape)
        for dimension in shape: tensor.dimensions.add().constant.size = dimension

    for name, shape, feature_type, mil_type in (
            ('maskedProjected', (1, 199, 1024), features.ArrayFeatureType.FLOAT32, mil.FLOAT32),
            ('positionEmbeddings', (1, 199, 1024), features.ArrayFeatureType.FLOAT32, mil.FLOAT32),
            ('frameMask', (1, 199), features.ArrayFeatureType.INT32, mil.INT32)):
        feature = model.description.input.add(name=name)
        feature.type.multiArrayType.dataType = feature_type
        feature.type.multiArrayType.shape.extend(shape)
        typed(function.inputs.add(name=name).type, shape, mil_type)
    output = model.description.output.add(name='hidden')
    output.type.multiArrayType.dataType = features.ArrayFeatureType.FLOAT32
    output.type.multiArrayType.shape.extend((1, 199, 1024))

    def operation(kind, sources, name, shape, dtype):
        op = block.operations.add(type=kind)
        for key, source in sources.items(): op.inputs[key].arguments.add(name=source)
        typed(op.outputs.add(name=name).type, shape, dtype)
        return op

    operation('add', {'x': 'maskedProjected', 'y': 'positionEmbeddings'}, 'sum', (1, 199, 1024), mil.FLOAT32)
    cast = operation('cast', {'x': 'frameMask'}, 'maskFloat', (1, 199), mil.FLOAT32)
    dtype = cast.inputs['dtype'].arguments.add().value
    typed(dtype.type, (), mil.STRING)
    dtype.immediateValue.tensor.strings.values.append('fp32')
    expand = operation('expand_dims', {'x': 'maskFloat'}, 'maskExpanded', (1, 199, 1), mil.FLOAT32)
    axes = expand.inputs['axes'].arguments.add().value
    typed(axes.type, (1,), mil.INT32)
    axes.immediateValue.tensor.ints.values.append(2)
    operation('add', {'x': 'sum', 'y': 'maskExpanded'}, 'hidden', (1, 199, 1024), mil.FLOAT32)
    block.outputs.append('hidden')
    return model, mil, features


class SavedAdmissionControls(unittest.TestCase):
    def test_actual_mil_integer_classes_require_canonical_identity(self):
        from coremltools.converters.mil.mil import types
        self.assertEqual(types.int32.__name__, 'int')
        self.assertIs(types.string_to_builtin('int32'), types.int32)
        self.assertEqual(types.builtin_to_string(types.int32), 'int32')
        for kind, canonical in ((types.int16, 'int16'), (types.int64, 'int64')):
            self.assertEqual(kind.__name__, 'int')
            self.assertIsNot(kind, types.int32)
            self.assertEqual(types.builtin_to_string(kind), canonical)
        with self.assertRaises(KeyError): types.string_to_builtin('int')

    def test_exact_serialized_int32_and_only_old_descriptor_failure(self):
        model, mil, features = spec_fixture()
        observed, evidence = subject.inspect_spec(model, mil, features)
        self.assertEqual(observed['inputs'][2]['dtype'], 'int32')
        self.assertEqual(evidence['milFrameMaskEnum'], mil.INT32)
        failed = {'schema': 'NativeIntegratedBodyStructureV1', 'passed': False, 'failureType': 'ValueError',
                  'observed': copy.deepcopy(observed)}
        failed['observed']['inputs'][2]['dtype'] = 'int'
        subject.require_only_descriptor_failure(failed, observed)
        failed['observed']['padCount'] = 1
        with self.assertRaises(ValueError): subject.require_only_descriptor_failure(failed, observed)

    def test_real_proto_int16_int64_and_wrong_feature_enum_are_rejected(self):
        for integer_name in ('INT16', 'INT64'):
            model, mil, features = spec_fixture()
            model.mlProgram.functions['main'].inputs[2].type.tensorType.dataType = getattr(mil, integer_name)
            with self.subTest(integer_name=integer_name), self.assertRaisesRegex(ValueError, 'exact input enums'):
                subject.inspect_spec(model, mil, features)
        model, mil, features = spec_fixture()
        model.description.input[2].type.multiArrayType.dataType = features.ArrayFeatureType.FLOAT32
        with self.assertRaisesRegex(ValueError, 'enum type'): subject.inspect_spec(model, mil, features)

    def test_proto_mask_connectivity_shape_and_conv_are_rejected(self):
        for kind in ('mask', 'shape', 'conv', 'undefined'):
            model, mil, features = spec_fixture()
            function = model.mlProgram.functions['main']
            block = function.block_specializations['CoreML7']
            if kind == 'mask': block.operations[-1].inputs['y'].arguments[0].name = 'sum'
            elif kind == 'shape': function.inputs[2].type.tensorType.dimensions[1].constant.size = 198
            elif kind == 'conv': block.operations[0].type = 'conv'
            else: block.operations[0].inputs['x'].arguments[0].name = 'missing'
            with self.subTest(kind=kind), self.assertRaises(ValueError): subject.inspect_spec(model, mil, features)

    def test_exact_copy_and_failed_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'saved'
            source.write_bytes(b'unchanged saved bytes')
            target = root / 'copied'
            expected = subject.shared.pin(source)
            copied = subject.copy_exact(source, expected, target, root)
            self.assertTrue(subject.shared.same_content(copied, expected))
            with self.assertRaises(ValueError): subject.copy_exact(source, expected, target, root)
            (root / 'work').mkdir()
            output = root / 'work' / 'export'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'admit', side_effect=ValueError('saved proof changed')):
                self.assertEqual(subject.main(['--output', str(output)]), 1)
                receipt = subject.shared.read_json(output / 'admission.json')
                self.assertFalse(receipt['complete'])
                self.assertEqual(receipt['forwardsCompleted'], 0)
                self.assertFalse(receipt['conversionExecuted'])
                with self.assertRaises(FileExistsError): subject.main(['--output', str(output)])


if __name__ == '__main__': unittest.main()
