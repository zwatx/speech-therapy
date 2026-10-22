# Native recording startup availability

When the startup check cannot inspect saved recordings, practice now shows **Recording is unavailable** and explains: “Cadence couldn’t check its saved recordings. Restart the app to try the check again.” Record and the ineffective empty-attempt retry stay unavailable. Restart starts another check; the message does not promise that restarting repairs storage.

The existing process-wide failure remains sticky. A read-only capturer availability value exposes that state without rescanning, resetting ownership or changing deletion policy. The session checks availability before requesting recording permission. Existing kept-take replay/discard, Close, guided Skip and Finish retain their original concurrency and cleanup guards. The original generic error remains available to older session owners.

## Verified behavior

On the dedicated arm64 iPhone SE (3rd generation), iOS 26.5 simulator, seven selected unit methods and four generated Release UI methods passed once, with no failures or skips. Official summaries, trees, action leaves and method details establish the exact methods, one run each, device and configuration. The tests cover sticky failure across owners, no permission or recorder allocation, ordinary transient retry, kept-take handling, manual guided navigation and actual Close cleanup. A generated integration test uses the real system capturer's failed directory scan with inert permission and recorder boundaries.

The four UI cases exercise ordinary practice and guided first review → manually selected practice → fresh recheck at normal and accessibility XXXL text sizes. Independent review inspected all 20 screenshots and 16 geometry records: the title and complete explanation are readable, guided navigation remains reachable, and the four terminal views show positive Close acknowledgements with no forbidden activity, owned takes or history writes. These are generated-host assertions and images, not live microphone, camera or recognition evidence or a VoiceOver audit.

The ordinary production Release app ran last. Its existing compact guided-repeat smoke passed once in 58.538 seconds: custom-word selection, first review, manual practice, fresh recheck, repeating the same five words with fresh observations, Close and unchanged history. This uses the production entry and bundled word resources, without recording or running a model. The screenshot shows a scrolled summary portion, not every summary row. No separate reinstall or installed-container byte audit followed the test.

All test groups ended with the simulator shut down and no owner signals, cleanup errors or remaining process-group members. Actual compiler records establish Debug/-Onone/DEBUG/testability for unit checks and Release/-O/no DEBUG/no testability for UI and ordinary app checks. The ordinary app's bundled word resources match the source bytes. Its standard project built both simulator architectures; the actual tests ran arm64. Production formatting passed; the test files retain 27 identical preexisting formatting findings, with zero new findings.

## Preserved failures and evidence

The first isolated Debug host failed to build because it excluded the production entry file while retaining an unused screen that depends on Debug configuration types defined there. The corrected host excludes that unused screen too; all verifier Swift files and test selectors remain byte-identical. That original failed build remains failed and ran no tests.

The ordinary Release compiler build succeeded, but its first post-build audit incorrectly assumed that only the package would also build x86_64. That failed root record is preserved. A separate read-only admission checks all six actual driver invocations, exact source lists, ordinary entry, resources and products; the compiler was not rerun to resolve this audit assumption.

Before copies, the five-file patch, source/product maps, formatting receipts, official results, screenshots, geometry and independent source/result reviews remain in `work/mobile-startup-cleanup-unavailable-20261016/`. The generated suite is under `execution-v2/`; ordinary restoration and its smoke are under `execution-v2/release/`.

The wider app goal remains active. This change establishes truthful recording availability and preserves guided navigation; it does not establish individual-sound correction or diagnosis. Apple English assets and earlier on-device capability are established, but Apple Speech authorization was denied before any recognition task. Bundled word recognition remains the previously verified default. No signing/account settings changed and no recordings were uploaded.
