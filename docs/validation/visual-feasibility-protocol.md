# Visual capture feasibility protocol

Status: executable protocol; no physical-device runs completed

This protocol evaluates camera framing and observability only. It does not
collect child speech, validate an articulation cue, authorize visual consent,
or support learner feedback. Until the clinical/privacy research protocol is
approved, use adult team members or contracted test participants with
non-patient data only.

## Evidence produced

The Debug learner app aggregates observations in memory and can export a
`visual-feasibility-report-v1` JSON file after the tester explicitly turns on
camera framing. Export finalizes the run, invalidates pending frame callbacks,
turns the camera off, and freezes one report before opening the file picker. The
report contains:

- scenario and protocol identifiers;
- OS, hardware, app, and runtime versions;
- total/usable frame counts and extraction failures;
- counts of framing/observability issues;
- bounded latency histograms and p95 bucket;
- worst thermal state and whether Low Power Mode was observed;
- fixed assertions that frames, raw landmarks, and derived evidence were not
  retained or uploaded.

It contains no images, video, mouth crops, raw landmarks, audio, learner ID,
device token, or prompted attempt result.

## Required equipment and setup

1. Use at least three supported physical hardware identifiers. Record at least
   two available OS patch versions where practical.
2. Use a reviewed Debug build from one immutable source revision. Record the
   source revision and build artifact hash in the evidence package.
3. Disable Low Power Mode and close other camera-intensive applications.
4. Enroll with a non-production placeholder context. Do not record or submit an
   audio attempt during the visual-only run.
5. Add these launch arguments in the Xcode scheme:

   ```text
   -CadenceVisualFeasibility
   -CadenceVisualScenario
   <scenario>
   ```

6. Confirm the app explains local processing before the permission prompt and
   that the tester must choose **Turn on camera framing**.

## Scenario matrix

Run each scenario long enough to export at least 100 processed frames per
hardware family. Relaunch with the next scenario value so reports never mix
conditions.

| Scenario argument | Controlled condition | Expected evidence |
| --- | --- | --- |
| `protocol-compliant` | Even front lighting, centered face, comfortable forward pose, visible mouth | At least 95% usable frames |
| `low-light` | Safe dim illumination while the face remains in view | At least 90% frames produce an explicit observability issue |
| `face-too-far` | Face visibly smaller than the guide | `faceTooFar` on at least 90% of frames |
| `face-too-close` | Face larger than the guide without touching the device | `faceTooClose` on at least 90% of frames |
| `face-off-center` | Face outside the center guide | `faceOffCenter` on at least 90% of frames |
| `head-turned` | Comfortable moderate head turn; never strain the participant | `headTurned` on at least 90% of frames |
| `mouth-covered` | Hand or opaque card safely obscures the mouth | `mouthLandmarksUnavailable` on at least 90% of frames |
| `multiple-faces` | Two consenting adult testers in frame | `multipleFaces` on at least 90% of frames |

Do not use braces, missing teeth, facial difference, skin tone, age, disability,
or another protected characteristic as an improvised challenge label. Those
slices require an approved sampling and equity analysis protocol.

## Lifecycle, privacy, and accessibility checks

Perform and record these separately from the aggregate scenario evaluator:

- Deny camera permission: audio practice remains available and no capture
  session starts.
- Background and foreground the app during permission and active capture: the
  camera indicator turns off promptly and stale results do not restore state.
- Interrupt the camera with an incoming-call simulation or another camera app:
  status remains honest and recovery behavior is recorded.
- With VoiceOver enabled, navigate from the prompt to the camera explanation,
  action, coaching, ready state, failure state, and report export without sight.
- Test Dynamic Type at the largest accessibility size and Reduce Motion.
- Inspect the app container before and after each run. No frame, video, mouth
  crop, or raw-landmark file may appear.
- Save exported aggregate JSON to an approved local study folder only.

## Network-capture check

Use an iOS remote virtual interface or equivalent reviewed device-capture tool:

```sh
rvictl -s <physical-device-udid>
sudo tcpdump -i rvi0 -w cadence-visual-feasibility.pcap
```

Start capture before turning on camera framing. Do not submit an audio attempt
and stop packet capture before exporting to Files or another app. The expected
result is no learner-app network connection caused by camera or Vision
processing. Record the pcap SHA-256 and a reviewer-signed connection summary;
never commit the pcap to this repository.

## Machine evaluation

Place exported JSON files in a private study directory outside the repository,
then run:

```sh
pnpm --filter @speech-therapy/visual-evaluation evaluate /approved/reports/*.json
```

The parser rejects unknown fields, retention/upload flags, inconsistent counts,
invalid timestamps, and malformed latency histograms. The default advancement
evaluation requires:

- every declared scenario;
- at least 100 frames per scenario on every included hardware identifier;
- at least three distinct hardware identifiers;
- one app build, one runtime, one target protocol, and unique session IDs across
  the comparison;
- at least 95% usable protocol-compliant frames;
- at least 90% expected challenge detection;
- no more than 1% extraction failures per scenario;
- p95 processing latency in the `le-100` ms bucket or better;
- latency measured for every non-extraction-failure frame in every report;
- worst thermal state no higher than `fair`;
- no Low Power Mode observation.

A passing JSON evaluation is necessary but not sufficient. It does not cover
memory, interruptions, VoiceOver, network behavior, subgroup equity, clinical
cue validity, unsupported claims, or prospective utility.

## Evidence package and decision

The Gate 2 capture-quality item remains open until the evidence package contains:

1. protocol version, source revision, build hash, and test-owner signatures;
2. validator output plus every original aggregate JSON report;
3. device/OS matrix and run deviations;
4. network-capture summary and pcap digest;
5. Instruments latency, memory, and thermal summary;
6. interruption and assistive-technology findings with resolved blockers;
7. privacy, security, accessibility, engineering, and clinical-safety sign-off.

Do not use schedule pressure or average performance to waive a failed scenario
or missing evidence artifact.
