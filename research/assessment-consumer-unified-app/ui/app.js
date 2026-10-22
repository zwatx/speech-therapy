'use strict';

(function () {
  // Recording limits match the processing contract: PCM16 mono 16 kHz WAV,
  // 1,600 to 64,000 samples, at most 132,096 bytes.
  const TARGET_RATE = 16000;
  const MAX_SECONDS = 4;
  const MAX_SAMPLES = TARGET_RATE * MAX_SECONDS;
  const MIN_SAMPLES = 1600;
  // Consistency bound from the declaration-pinned admission policy, not a score.
  const POLICY_MIN_RMS = 0.001;
  const MIN_INPUT_RATE = 8000;
  const MAX_INPUT_RATE = 192000;
  const ANTI_ALIAS_HZ = 7200;
  const FINISH_WAIT_MS = 1500;
  const SAFETY_MARGIN_MS = 1000;
  const MAX_AUDIO_BYTES = 132096;
  const MAX_REQUEST_BYTES = 200000;
  const MAX_RESPONSE_BYTES = 16000;
  const MAX_TAKES = 2;
  const CSRF_HEADER = 'X-Consumer-CSRF';
  const FEEDBACK_PATH = '/api/feedback';
  const FEEDBACK_DECLARATION_PATH = '/api/feedback-declaration';
  // Successor policy for schema 2 requests with a declared practice context.
  // A v1 declaration is refused by normalizeDeclaration.
  const FEEDBACK_POLICY_ID = 'consumer-recording-feedback-v2';

  const HEX64 = /^[0-9a-f]{64}$/;
  const PIN_KEYS = [
    'admissionSourceSha256', 'bridgeSourceSha256', 'serviceSourceSha256',
    'supervisorSourceSha256', 'policySha256', 'modelManifestSha256',
  ];
  // Compare every core source and policy pin repeated by the actual API.
  const FEEDBACK_PIN_KEYS = PIN_KEYS;
  const FEEDBACK_HASH_KEYS = ['feedbackSourceSha256', 'wrapperSourceSha256', 'contentSha256'];
  const CLAIM_KEYS = [
    'speechPresenceVerified', 'requestedWordVerified', 'promptMatchingValidated',
    'intendedChildAccuracyEstablished', 'qualifiedApprovalEstablished',
    'learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible',
    'authenticProvenanceEstablished', 'diagnosisProvided', 'pronunciationCorrectnessAssessed',
  ];
  const RESPONSE_KEYS = [
    'schemaVersion', 'kind', 'status', 'reason', 'stages', 'targetAssessment',
    'suggestionCodes', 'binding', 'claimLimits', 'elapsedMilliseconds',
  ];
  const STAGES_KEYS = ['capture', 'speech', 'word'];
  const STAGE_KEYS = ['state', 'reason'];
  const METRIC_KEYS = ['sampleCount', 'durationMilliseconds', 'rms', 'rmsDbfs', 'peak', 'railSamples', 'clippedFraction'];
  const CAPTURE_KEYS = [...STAGE_KEYS, ...METRIC_KEYS];
  const BINDING_KEYS = [
    'attemptId', 'requestSha256', 'audioSha256', 'promptSha256', 'evidenceSha256',
    ...FEEDBACK_PIN_KEYS, 'feedbackSourceSha256', 'wrapperSourceSha256', 'feedbackPolicySha256', 'contentSha256',
  ];
  // Everything in the binding except the evidence digest, which the page cannot know.
  const BOUND_KEYS = BINDING_KEYS.filter((k) => k !== 'evidenceSha256');
  const DECLARATION_KEYS = ['schemaVersion', 'csrfToken', 'pins', 'feedbackPolicy', ...FEEDBACK_HASH_KEYS, 'processingAvailable'];

  // Closed reason codes, grouped by what each one says about the three stages.
  const WORD_STATE = {
    requested_word_not_matched: 'model_not_matched',
    single_word_required: 'not_single_word',
    recognition_uncertain: 'uncertain',
    recognition_incomplete: 'uncertain',
  };
  const MODEL_FAILURES = ['worker_timeout', 'worker_crash', 'model_unavailable', 'recognition_failed'];
  const SERVICE_FAILURES = [
    'invalid_evidence', 'busy', 'timeout', 'source_binding_failed', 'assessment_failed',
    'invalid_request', 'cleanup_unconfirmed',
  ];

  const CAN_STILL = 'You can still record, listen and compare.';
  const quote = (word) => `“${word}”`;

  // Copy for each word-check outcome. Titles describe what the model reported,
  // never how the word was said.
  const RESULTS = {
    matched: {
      title: (w) => `Recognition matched ${quote(w)}`,
      text: 'The model detected speech, and its whole-word recognition matched the word you are practicing.',
      short: 'Recognition matched',
    },
    not_matched: {
      title: (w) => `Recognition did not match ${quote(w)}`,
      text: 'The model detected speech, but its whole-word recognition did not match. Recognition can miss words that were said clearly, so this is not a judgment of how it was said.',
      short: 'Recognition did not match',
    },
    not_single: {
      title: (w) => `Recognition did not match ${quote(w)}`,
      text: 'The model detected speech, but its recognition was not a single word.',
      short: 'Recognition did not match',
    },
    uncertain: {
      title: () => 'Word check was unsure',
      text: 'The model detected speech, but its recognition was not confident enough to give a whole-word result.',
      short: 'Word check unsure',
    },
    no_speech: {
      title: () => 'The model did not detect speech',
      text: 'So the word was not checked. If you did say it, make sure the microphone is not muted or too far away.',
      short: 'Model did not detect speech',
    },
    quiet: {
      title: () => 'Too quiet to check',
      text: 'The recording level was very low, so the word check did not run. Moving a little closer to the microphone may help.',
      short: 'Too quiet to check',
    },
    loud: {
      title: () => 'Too loud to check',
      text: 'Some recording samples reached the maximum numeric level, so the word check did not run.',
      short: 'Too loud to check',
    },
    unusable: {
      title: () => 'This recording could not be used',
      text: 'The word check could not read it.',
      short: 'Could not be used',
    },
  };
  const KIND_BY_REASON = {
    requested_word_not_matched: 'not_matched',
    single_word_required: 'not_single',
    recognition_uncertain: 'uncertain',
    recognition_incomplete: 'uncertain',
    speech_not_detected: 'no_speech',
    silence: 'quiet',
    clipping: 'loud',
    invalid_audio: 'unusable',
  };

  // `retry` is true only where nothing was observed, so checking the same try
  // again cannot be used to fish for a different word result.
  const DID_NOT_FINISH = { text: 'The check did not finish, so there is no word result.', retry: true };
  const TOOK_TOO_LONG = { text: 'The check took too long and was stopped.', retry: true };
  const FAILURES = {
    busy: { title: 'Computer busy', text: 'The computer was checking another recording.', retry: true },
    timeout: TOOK_TOO_LONG,
    worker_timeout: TOOK_TOO_LONG,
    worker_crash: DID_NOT_FINISH,
    recognition_failed: DID_NOT_FINISH,
    assessment_failed: DID_NOT_FINISH,
    invalid_evidence: DID_NOT_FINISH,
    model_unavailable: { text: 'The recognition model is not available on this computer.', retry: false },
    cleanup_unconfirmed: { text: 'Word check is paused on this computer until someone looks into it.', retry: false },
    source_binding_failed: { text: 'The word check setup could not be confirmed. Reload the page to use word check again.', retry: false },
    invalid_request: { text: 'This try could not be sent for checking.', retry: false },
  };

  // Failures before a reply could be read.
  const OUTCOME = {
    invalid: { text: 'The reply from word check could not be verified, so no result is shown.', retry: true },
    unreachable: { text: 'Word check on this computer could not be reached.', retry: true },
    failed: DID_NOT_FINISH,
    busy: { title: 'Computer busy', text: 'Word check is busy with another recording.', retry: true },
    session: { text: 'The page needed to reconnect to word check.', retry: true, refresh: true },
    rejected: { text: 'This try could not be sent for checking.', retry: false },
    tooLarge: { text: 'This recording is too large to check.', retry: false, next: 'Record a fresh try.' },
  };

  const SUGGESTIONS = {
    record_again: () => 'Record a fresh try.',
    review_recording: () => 'Play your try to hear what was recorded.',
    reduce_recording_level: () => 'Move back a little from the microphone, or say it a little more softly.',
    listen_to_example: () => 'Play the example, then your try, and listen to both.',
    say_one_word: (w) => `Say just ${quote(w)} on its own.`,
    try_again: () => 'Have another go with a fresh try.',
    retry_later: (w, retry) => (retry ? 'Check again in a moment.' : 'Word check may work again later.'),
    processing_unavailable: () => CAN_STILL,
    continue_practice: () => 'Keep practicing: compare your try with the example by ear, or try another word.',
  };

  const STOPPED_TEXT = 'No result will be shown for that check. The computer may still finish it in the background.';
  const NEW_RECORDING_STOPPED_TEXT = 'The check stopped when a new recording started. No result will be shown for that check.';
  const PAUSED_TEXT = 'Paused because the page was hidden. The microphone and camera were turned off and your tries were cleared.';
  const SETTINGS_CLEARED_TEXT = 'Your tries were cleared because the word check settings changed.';
  const CHOOSE_WHO_TEXT = 'Choose who is practicing first.';
  // In free practice the shared choice sits in Say it, not beside this box.
  const CHOOSE_WHO_FREE_TEXT = 'Choose who is practicing first, above Record.';
  const CONTEXT_CLEARED_TEXT = 'Your tries were cleared because who is practicing changed.';
  const SOUND_SETTINGS_CLEARED_TEXT = 'The sound comparison was turned off. Tick its boxes again to use it.';

  const POSITION = { beginning: 'beginning', middle: 'middle', end: 'ending' };

  // ---------- guided state pure begin ----------
// Pure section intended for the existing app.js IIFE. No serving or module change.
  const GUIDED_CANONICAL_CATALOG = [{"id":"r-beginning-rabbit","word":"rabbit","sourceWord":"rabbit","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"rabbit","words":[{"text":"rabbit","phones":["R","AE","B","AH","T"]}],"targets":[{"id":"r-beginning-rabbit","wordIndex":0,"phoneIndex":0,"targetPhone":"R"}]},"promptSha256":"85844397a23c2a18c9a92a428623c1facdf9282230c66994274c51c87a138ac8"},{"id":"r-middle-bread","word":"bread","sourceWord":"bread","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"bread","words":[{"text":"bread","phones":["B","R","EH","D"]}],"targets":[{"id":"r-middle-bread","wordIndex":0,"phoneIndex":1,"targetPhone":"R"}]},"promptSha256":"7910f87e3a252ae0b3a41dfa45649a122c461b7b1ca7fda67f6c309ab4c56383"},{"id":"r-end-door","word":"door","sourceWord":"door","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"door","words":[{"text":"door","phones":["D","AO","R"]}],"targets":[{"id":"r-end-door","wordIndex":0,"phoneIndex":2,"targetPhone":"R"}]},"promptSha256":"af488f0dd5b588d7fc99bfaa848911842108ca9f005c37d15fb8ba5e5c279ef2"},{"id":"b-beginning-baby","word":"baby","sourceWord":"baby","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"baby","words":[{"text":"baby","phones":["B","EY","B","IY"]}],"targets":[{"id":"b-beginning-baby","wordIndex":0,"phoneIndex":0,"targetPhone":"B"}]},"promptSha256":"85b5d68283cab50ee5950f66d5cc2e63da5473cc4d33ab541cd6e0910e8e2054"},{"id":"b-middle-baby","word":"baby","sourceWord":"baby","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"baby","words":[{"text":"baby","phones":["B","EY","B","IY"]}],"targets":[{"id":"b-middle-baby","wordIndex":0,"phoneIndex":2,"targetPhone":"B"}]},"promptSha256":"5474df711b0cf440d3909fcc6503573b52302e759500aa3d0971f6907e00da51"},{"id":"n-middle-banana","word":"banana","sourceWord":"banana","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"banana","words":[{"text":"banana","phones":["B","AH","N","AE","N","AH"]}],"targets":[{"id":"n-middle-banana","wordIndex":0,"phoneIndex":2,"targetPhone":"N"}]},"promptSha256":"ddf904bbec2f14c69082db3e59c1c45fcc017ce605b1a111f1f8a546cd8fc421"},{"id":"k-middle-backpack","word":"backpack","sourceWord":"backpack","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"backpack","words":[{"text":"backpack","phones":["B","AE","K","P","AE","K"]}],"targets":[{"id":"k-middle-backpack","wordIndex":0,"phoneIndex":2,"targetPhone":"K"}]},"promptSha256":"f5f54cac611052db5cdf8c562b5ed917f0a40080b93ca5dac7d2b826ec3ed39e"},{"id":"k-end-backpack","word":"backpack","sourceWord":"backpack","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"backpack","words":[{"text":"backpack","phones":["B","AE","K","P","AE","K"]}],"targets":[{"id":"k-end-backpack","wordIndex":0,"phoneIndex":5,"targetPhone":"K"}]},"promptSha256":"62f03ef1f1188d6e332865499593783e5508fbaef48e77c3664b092fe751fdb1"},{"id":"s-beginning-sky","word":"sky","sourceWord":"sky","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"sky","words":[{"text":"sky","phones":["S","K","AY"]}],"targets":[{"id":"s-beginning-sky","wordIndex":0,"phoneIndex":0,"targetPhone":"S"}]},"promptSha256":"f0c78e9754e628629ee36ae156a22be854f6d1414161efdc14e3e1f8ff715fbb"},{"id":"v-beginning-vase","word":"vase","sourceWord":"vase","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"vase","words":[{"text":"vase","phones":["V","EY","S"]}],"targets":[{"id":"v-beginning-vase","wordIndex":0,"phoneIndex":0,"targetPhone":"V"}]},"promptSha256":"955a86195ecb2ef2008e1ac1e7870c6fa6e12593fd36a4bac3db0c40a7f953d4"},{"id":"y-beginning-yo-yo","word":"yo-yo","sourceWord":"yoyo","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"yo-yo","words":[{"text":"yo-yo","phones":["Y","OW","Y","OW"]}],"targets":[{"id":"y-beginning-yo-yo","wordIndex":0,"phoneIndex":0,"targetPhone":"Y"}]},"promptSha256":"c697644c9e5a1408c5c6b14fa342392d5c5a2b09a5290b1248f8899a0906303e"},{"id":"th-beginning-thumb","word":"thumb","sourceWord":"thumb","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"thumb","words":[{"text":"thumb","phones":["TH","AH","M"]}],"targets":[{"id":"th-beginning-thumb","wordIndex":0,"phoneIndex":0,"targetPhone":"TH"}]},"promptSha256":"e3f42848afc64fb0ec262bbf67fdfeacc99ab72d246e3595a2d9c0c115e07bbb"},{"id":"voiced-th-middle-feather","word":"feather","sourceWord":"feather","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"feather","words":[{"text":"feather","phones":["F","EH","DH","ER"]}],"targets":[{"id":"voiced-th-middle-feather","wordIndex":0,"phoneIndex":2,"targetPhone":"DH"}]},"promptSha256":"770efea763c4e9a7bc8f5b4d3b6b86fd3b2c683dfafe66448ad94ec09f0a1e05"},{"id":"ng-end-ring","word":"ring","sourceWord":"ring","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"ring","words":[{"text":"ring","phones":["R","IH","NG"]}],"targets":[{"id":"ng-end-ring","wordIndex":0,"phoneIndex":2,"targetPhone":"NG"}]},"promptSha256":"f1f28ef21f563b6f99e6e8d2ce76a96c07cb8e79c64f7131f8ff90170f9a7b1d"},{"id":"zh-middle-treasure","word":"treasure","sourceWord":"treasure","processingPrompt":{"schemaVersion":2,"language":"en","transcript":"treasure","words":[{"text":"treasure","phones":["T","R","EH","ZH","ER"]}],"targets":[{"id":"zh-middle-treasure","wordIndex":0,"phoneIndex":3,"targetPhone":"ZH"}]},"promptSha256":"b65604125114d61043251741667162752d4c542feb788aff44a752057b0e05e7"}];
  const GUIDED_ATTEMPT_LIMIT = 128;
  const GUIDED_PIN_KEYS = ['admissionSourceSha256', 'bridgeSourceSha256', 'serviceSourceSha256', 'supervisorSourceSha256', 'policySha256', 'modelManifestSha256'];
  const GUIDED_HASH_KEYS = ['feedbackSourceSha256', 'wrapperSourceSha256', 'feedbackPolicySha256', 'contentSha256'];
  const GUIDED_LOCAL_TERMINALS = ['permission_denied', 'permission_cancelled', 'capture_cancelled', 'capture_failed', 'recorded_discarded', 'check_failed', 'check_cancelled', 'invalid_response'];
  const GUIDED_REASONS = [null, 'requested_word_not_matched', 'single_word_required', 'recognition_uncertain', 'recognition_incomplete', 'speech_not_detected', 'silence', 'clipping', 'invalid_audio', 'worker_timeout', 'worker_crash', 'model_unavailable', 'recognition_failed', 'invalid_evidence', 'busy', 'timeout', 'source_binding_failed', 'assessment_failed', 'invalid_request', 'cleanup_unconfirmed'];
  const GUIDED_SUGGESTIONS = ['record_again', 'review_recording', 'reduce_recording_level', 'listen_to_example', 'say_one_word', 'try_again', 'retry_later', 'processing_unavailable', 'continue_practice'];
  const GUIDED_WORD_STATES = ['model_matched', 'model_not_matched', 'uncertain', 'not_single_word'];
  // Owner decision: uncertain/not-single-word are categories, not whole-word results.
  const GUIDED_LEXICAL_STATES = ['model_matched', 'model_not_matched'];
  const guidedToken = (v) => typeof v === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(v);
  const guidedInt = (v) => Number.isSafeInteger(v) && v >= 0;
  const guidedHex = (v) => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v);
  const guidedObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const guidedExact = (v, keys) => guidedObject(v) && Object.keys(v).length === keys.length && keys.every((k) => Object.hasOwn(v, k));
  function guidedCanonical(v) {
    if (Array.isArray(v)) return '[' + v.map(guidedCanonical).join(',') + ']';
    if (guidedObject(v)) return '{' + Object.keys(v).sort().map((k) => JSON.stringify(k) + ':' + guidedCanonical(v[k])).join(',') + '}';
    return JSON.stringify(v);
  }
  function guidedFreeze(v) {
    if (v && typeof v === 'object' && !Object.isFrozen(v)) {
      Object.values(v).forEach(guidedFreeze);
      Object.freeze(v);
    }
    return v;
  }
  function guidedRoster(catalog) {
    if (!Array.isArray(catalog) || catalog.length !== 15) return null;
    const roster = [];
    for (let i = 0; i < 15; i++) {
      const p = catalog[i], expected = GUIDED_CANONICAL_CATALOG[i];
      if (!guidedObject(p) || p.id !== expected.id || p.word !== expected.word || p.sourceWord !== expected.sourceWord) return null;
      try {
        if (guidedCanonical(p.processingPrompt) !== guidedCanonical(expected.processingPrompt)) return null;
      } catch (_) { return null; }
      const prior = roster.find((r) => r.word === expected.word);
      if (prior) prior.catalogPromptIds.push(expected.id);
      else roster.push({ itemId: expected.id, word: expected.word, promptSha256: expected.promptSha256, catalogPromptIds: [expected.id] });
    }
    return roster.length === 13 ? roster : null;
  }
  // Declared practice context: exactly {kind:'adult'} or {kind:'child', ageYears:6..12}.
  // The person's own choice, never a verified age. Adult carries no number.
  const PRACTICE_CHILD_VALUES = ['child-6', 'child-7', 'child-8', 'child-9', 'child-10', 'child-11', 'child-12'];
  function practiceContextValid(c) {
    if (!guidedObject(c)) return false;
    if (c.kind === 'adult') return guidedExact(c, ['kind']);
    return c.kind === 'child' && guidedExact(c, ['kind', 'ageYears']) && Number.isInteger(c.ageYears) && c.ageYears >= 6 && c.ageYears <= 12;
  }
  // A fresh frozen canonical copy, or null; never an alias of the caller's object.
  function practiceContextCopy(c) {
    if (!practiceContextValid(c)) return null;
    return Object.freeze(c.kind === 'adult' ? { kind: 'adult' } : { kind: 'child', ageYears: c.ageYears });
  }
  // Structural equality of two valid contexts; null or invalid never matches.
  function practiceContextSame(a, b) {
    return practiceContextValid(a) && practiceContextValid(b) && guidedCanonical(a) === guidedCanonical(b);
  }
  // Select option value -> context. Only the exact closed option strings map.
  function practiceContextOf(value) {
    if (value === 'adult') return practiceContextCopy({ kind: 'adult' });
    const i = PRACTICE_CHILD_VALUES.indexOf(value);
    return i === -1 ? null : practiceContextCopy({ kind: 'child', ageYears: i + 6 });
  }
  function practiceContextValue(c) {
    if (!practiceContextValid(c)) return '';
    return c.kind === 'adult' ? 'adult' : `child-${c.ageYears}`;
  }
  function practiceContextLabel(c) {
    if (!practiceContextValid(c)) return '';
    return c.kind === 'adult' ? 'Adult' : `Child, age ${c.ageYears}`;
  }
  // Equality key, not a security digest. Uses only bounded pins/IDs/digests/context.
  // CSRF deliberately excluded. No transcript or canonical request retained in state.
  function guidedFingerprint(catalog, declaration, practiceContext, setupGeneration) {
    const roster = guidedRoster(catalog);
    if (!roster || !guidedObject(declaration) || !guidedExact(declaration.pins, GUIDED_PIN_KEYS) || !GUIDED_PIN_KEYS.every((k) => guidedHex(declaration.pins[k])) || !GUIDED_HASH_KEYS.every((k) => guidedHex(declaration[k])) || !practiceContextValid(practiceContext) || !guidedInt(setupGeneration)) return null;
    return guidedCanonical({ practiceContext: practiceContextCopy(practiceContext), setupGeneration, roster, catalogBindings: GUIDED_CANONICAL_CATALOG.map((p) => ({ id: p.id, promptSha256: p.promptSha256 })), pins: declaration.pins, hashes: Object.fromEntries(GUIDED_HASH_KEYS.map((k) => [k, declaration[k]])) });
  }
  function guidedRound(id, context, sessionId, generation, kind) {
    return { id, sessionId, generation, kind, fingerprint: context.fingerprint, plannedItemIds: context.roster.map((r) => r.itemId), dispositionsByItemId: Object.fromEntries(context.roster.map((r) => [r.itemId, { kind: 'not_reached', primaryAttemptId: null, observation: null, reason: null }])), finishedEarly: false };
  }
  // IDs and generations are allocated by the existing controller, never here.
  function makeGuidedSession(catalog, declaration, practiceContext, options) {
    if (!guidedObject(options) || options.optIn !== true || declaration?.processingAvailable !== true || !guidedToken(options.id) || !guidedInt(options.generation)) return null;
    const fingerprint = guidedFingerprint(catalog, declaration, practiceContext, options.setupGeneration);
    if (fingerprint === null) return null;
    const context = { practiceContext: practiceContextCopy(practiceContext), setupGeneration: options.setupGeneration, fingerprint, roster: guidedRoster(catalog) };
    return guidedFreeze({ version: 1, id: options.id, generation: options.generation, context, phase: 'first_round', currentItemId: context.roster[0].itemId, first: guidedRound(options.id + '-first', context, options.id, options.generation, 'first'), recheck: null, attempts: [] });
  }
  function guidedCurrentRound(s) { return s.phase === 'first_round' ? s.first : s.phase === 'recheck' ? s.recheck : null; }
  function guidedPurpose(s) { return s.phase === 'first_round' ? 'first' : s.phase === 'recheck' ? 'recheck' : s.phase === 'practice' ? 'practice' : null; }
  function guidedOwner(s, attemptId) {
    const a = s?.attempts.find((v) => v.id === attemptId);
    if (!a) return null;
    return guidedFreeze({ sessionId: s.id, generation: s.generation, roundId: a.roundId, itemId: a.itemId, attemptId: a.id, captureId: a.captureId, takeId: a.takeId, setupGeneration: s.context.setupGeneration, fingerprint: s.context.fingerprint });
  }
  function guidedOwns(s, owner) {
    if (!s || !guidedExact(owner, ['sessionId', 'generation', 'roundId', 'itemId', 'attemptId', 'captureId', 'takeId', 'setupGeneration', 'fingerprint'])) return false;
    const a = s.attempts.find((v) => v.id === owner.attemptId);
    return !!a && a.terminalCode === null && a.itemId === s.currentItemId && a.purpose === guidedPurpose(s) && a.roundId === (guidedCurrentRound(s)?.id || null) && Object.entries(guidedOwner(s, a.id)).every(([k, v]) => owner[k] === v);
  }
  // Call ONLY after interpretFeedback's final validation gate has passed, including
  // unavailable service/model replies. Projection is metadata, not a validator.
  function guidedObservationOfValidated(d, fingerprint) {
    const stage = (s) => ({ state: s.state, reason: s.reason });
    return guidedFreeze({ status: d.status, reason: d.reason, capture: stage(d.stages.capture), speech: stage(d.stages.speech), word: stage(d.stages.word), targetAssessment: stage(d.targetAssessment), boundedSuggestionCodes: [...d.suggestionCodes], fingerprint });
  }
  // Storage fence for the typed adapter. Strict public response/binding validation
  // remains exclusively in the existing parser. No metrics/text enter this section.
  function guidedTypedObservation(o, fingerprint) {
    if (!guidedExact(o, ['status', 'reason', 'capture', 'speech', 'word', 'targetAssessment', 'boundedSuggestionCodes', 'fingerprint']) || o.fingerprint !== fingerprint || !['observed', 'unavailable'].includes(o.status) || !GUIDED_REASONS.includes(o.reason)) return false;
    const states = { capture: ['observed', 'unavailable'], speech: ['model_detected', 'model_not_detected', 'not_run', 'unavailable'], word: [...GUIDED_WORD_STATES, 'not_run', 'unavailable'], targetAssessment: ['unsupported', 'not_performed'] };
    for (const [k, values] of Object.entries(states)) {
      if (!guidedExact(o[k], ['state', 'reason']) || !values.includes(o[k].state) || ![...GUIDED_REASONS, 'unsupported_target', 'not_validated'].includes(o[k].reason)) return false;
    }
    return Array.isArray(o.boundedSuggestionCodes) && o.boundedSuggestionCodes.length <= 3 && new Set(o.boundedSuggestionCodes).size === o.boundedSuggestionCodes.length && o.boundedSuggestionCodes.every((v) => GUIDED_SUGGESTIONS.includes(v));
  }
  function guidedDisposition(o) {
    if (['silence', 'clipping', 'invalid_audio'].includes(o.reason)) return 'recording_issue';
    if (o.status === 'unavailable') return 'check_unavailable';
    return { model_matched: 'model_matched', model_not_matched: 'model_not_matched', uncertain: 'recognition_uncertain', not_single_word: 'not_single_supported_word', not_run: 'speech_not_detected' }[o.word.state];
  }
  function guidedSettle(s, a, code, observation = null) {
    if (a.terminalCode !== null) return;
    a.terminalCode = code;
    a.observation = observation;
    if (a.submitted && a.purpose !== 'practice') {
      const round = a.purpose === 'first' ? s.first : s.recheck;
      if (round.dispositionsByItemId[a.itemId].primaryAttemptId === a.id) round.dispositionsByItemId[a.itemId] = { kind: observation ? guidedDisposition(observation) : 'check_unavailable', primaryAttemptId: a.id, observation, reason: observation?.reason ?? code };
    }
  }
  function guidedCloseOpen(s) {
    for (const a of s.attempts) if (a.terminalCode === null) guidedSettle(s, a, a.submitted ? 'check_cancelled' : a.takeId === null ? 'capture_cancelled' : 'recorded_discarded');
  }
  function applyGuidedEvent(state, event) {
    const result = (s, accepted, reason = null, actions = []) => guidedFreeze({ state: s, accepted, reason, actions });
    if (!state || !guidedObject(event)) return result(state, false, 'no_session');
    if (['end', 'settings_changed', 'hidden', 'pagehide', 'free_practice'].includes(event.type)) {
      // Finalization is reported once for still-open attempts before metadata clear.
      return result(null, true, null, [{ type: 'clear_media' }, { type: 'terminate_attempts', attempts: state.attempts.filter((a) => a.terminalCode === null).map((a) => ({ id: a.id, terminalCode: a.submitted ? 'check_cancelled' : a.takeId === null ? 'capture_cancelled' : 'recorded_discarded' })) }]);
    }
    if (event.type === 'context_refresh') {
      const fp = guidedFingerprint(event.catalog, event.declaration, event.practiceContext, event.setupGeneration);
      if (fp !== state.context.fingerprint || !practiceContextSame(event.practiceContext, state.context.practiceContext) || event.declaration?.processingAvailable !== true || event.optIn !== true) {
        const cleared = applyGuidedEvent(state, { type: 'end' });
        return result(null, true, 'context_changed', [...cleared.actions, { type: 'require_new_session' }]);
      }
      return result(state, true); // process token remains solely with the controller
    }
    const s = JSON.parse(JSON.stringify(state)), round = guidedCurrentRound(s), purpose = guidedPurpose(s);
    const fail = (reason) => result(state, false, reason);
    const finish = (actions = []) => result(guidedFreeze(s), true, null, actions);
    if (event.type === 'record_start') {
      if (!purpose || (round && round.dispositionsByItemId[s.currentItemId].kind !== 'not_reached')) return fail('round_item_closed');
      if (s.attempts.length >= GUIDED_ATTEMPT_LIMIT) return fail('attempt_limit');
      if (!guidedToken(event.attemptId) || !guidedToken(event.captureId) || s.attempts.some((a) => a.id === event.attemptId || a.captureId === event.captureId)) return fail('reused_identifier');
      if (s.attempts.some((a) => a.terminalCode === null && a.takeId === null)) return fail('capture_pending');
      s.attempts.push({ id: event.attemptId, purpose, roundId: round?.id || null, itemId: s.currentItemId, captureId: event.captureId, takeId: null, terminalCode: null, submitted: false, posted: false, observation: null, audioSha256: null });
      return finish([{ type: 'start_capture', owner: guidedOwner(s, event.attemptId) }]);
    }
    if (['capture_ready', 'attempt_terminal', 'check', 'post_started', 'observation'].includes(event.type)) {
      if (!guidedOwns(state, event.owner)) return fail('stale_owner');
      const a = s.attempts.find((v) => v.id === event.owner.attemptId);
      if (event.type === 'capture_ready') {
        if (a.takeId !== null || a.submitted || !guidedToken(event.takeId) || !guidedHex(event.audioSha256)) return fail('invalid_capture');
        if (s.attempts.some((v) => v.takeId === event.takeId)) return fail('reused_take');
        a.takeId = event.takeId; a.audioSha256 = event.audioSha256;
        return finish();
      }
      if (event.type === 'attempt_terminal') {
        if (!GUIDED_LOCAL_TERMINALS.includes(event.code) || (a.submitted ? !['check_failed', 'check_cancelled', 'invalid_response'].includes(event.code) : a.takeId === null ? !['permission_denied', 'permission_cancelled', 'capture_cancelled', 'capture_failed'].includes(event.code) : event.code !== 'recorded_discarded')) return fail('invalid_terminal');
        guidedSettle(s, a, event.code); return finish();
      }
      if (event.type === 'check') {
        if (a.takeId === null || a.submitted || (round && round.dispositionsByItemId[a.itemId].kind !== 'not_reached')) return fail('already_submitted_or_unready');
        a.submitted = true;
        if (round) round.dispositionsByItemId[a.itemId] = { kind: 'check_unavailable', primaryAttemptId: a.id, observation: null, reason: 'check_pending' };
        return finish([{ type: 'submit_check', owner: guidedOwner(s, a.id) }]);
      }
      if (event.type === 'post_started') {
        if (!a.submitted || a.posted) return fail('already_posted_or_unsubmitted');
        a.posted = true; return finish();
      }
      if (!a.submitted || !a.posted || !guidedTypedObservation(event.observation, s.context.fingerprint)) return fail('invalid_observation');
      const observation = JSON.parse(JSON.stringify(event.observation));
      if (!guidedDisposition(observation)) return fail('invalid_observation');
      guidedSettle(s, a, 'verified_response', observation); return finish();
    }
    if (event.type === 'skip' || event.type === 'next') {
      if (!round) return fail('no_active_round');
      const disposition = round.dispositionsByItemId[s.currentItemId];
      if (event.type === 'next' && (disposition.kind === 'not_reached' || s.attempts.some((a) => a.itemId === s.currentItemId && a.submitted && a.terminalCode === null))) return fail('item_not_terminal');
      if (event.type === 'skip' && disposition.kind !== 'not_reached') return fail('round_item_closed');
      guidedCloseOpen(s);
      if (event.type === 'skip') round.dispositionsByItemId[s.currentItemId] = { kind: 'skipped', primaryAttemptId: null, observation: null, reason: null };
      const index = round.plannedItemIds.indexOf(s.currentItemId) + 1;
      s.currentItemId = round.plannedItemIds[index] || null;
      if (s.currentItemId === null) s.phase = purpose === 'first' ? 'summary' : 'comparison';
      return finish([{ type: 'clear_media' }]);
    }
    if (event.type === 'finish_round') {
      if (!round) return fail('no_active_round');
      guidedCloseOpen(s); round.finishedEarly = round.plannedItemIds.some((id) => round.dispositionsByItemId[id].kind === 'not_reached');
      s.phase = purpose === 'first' ? 'summary' : 'comparison'; s.currentItemId = null;
      return finish([{ type: 'clear_media' }]);
    }
    if (event.type === 'practice_word') {
      if (!['summary', 'comparison', 'practice'].includes(s.phase) || !s.context.roster.some((r) => r.itemId === event.itemId)) return fail('invalid_practice');
      guidedCloseOpen(s); s.phase = 'practice'; s.currentItemId = event.itemId;
      return finish([{ type: 'clear_media' }]);
    }
    if (event.type === 'return_summary') {
      if (s.phase !== 'practice') return fail('not_practice');
      guidedCloseOpen(s); s.phase = s.recheck ? 'comparison' : 'summary'; s.currentItemId = null;
      return finish([{ type: 'clear_media' }]);
    }
    if (event.type === 'start_recheck') {
      if (!['summary', 'practice'].includes(s.phase) || s.recheck !== null) return fail('recheck_already_started_or_unready');
      guidedCloseOpen(s); s.recheck = guidedRound(s.id + '-recheck', s.context, s.id, s.generation, 'recheck'); s.phase = 'recheck'; s.currentItemId = s.context.roster[0].itemId;
      return finish([{ type: 'clear_media' }]);
    }
    return fail('unknown_event');
  }
  function summarizeRound(round, attempts = []) {
    const rows = round.plannedItemIds.map((itemId) => ({ itemId, ...round.dispositionsByItemId[itemId] }));
    const counts = Object.fromEntries(['model_matched', 'model_not_matched', 'recognition_uncertain', 'not_single_supported_word', 'speech_not_detected', 'recording_issue', 'check_unavailable', 'skipped', 'not_reached'].map((k) => [k, rows.filter((r) => r.kind === k).length]));
    const owned = attempts.filter((a) => a.roundId === round.id);
    return guidedFreeze({ planned: 13, rows, counts, recordingAttempts: owned.length, submittedChecks: owned.filter((a) => a.submitted).length, httpPosts: owned.filter((a) => a.posted).length, verifiedResponses: owned.filter((a) => a.terminalCode === 'verified_response').length, lexicalObservations: rows.filter((r) => r.observation && GUIDED_LEXICAL_STATES.includes(r.observation.word.state)).length });
  }
  function compareRounds(first, recheck, attempts = []) {
    if (!first || !recheck || first.kind !== 'first' || recheck.kind !== 'recheck' || first.sessionId !== recheck.sessionId || first.generation !== recheck.generation || first.id === recheck.id || first.fingerprint !== recheck.fingerprint || guidedCanonical(first.plannedItemIds) !== guidedCanonical(recheck.plannedItemIds)) return null;
    const rows = first.plannedItemIds.map((itemId) => {
      const a = first.dispositionsByItemId[itemId], b = recheck.dispositionsByItemId[itemId];
      const complete = !!a.observation && !!b.observation && GUIDED_LEXICAL_STATES.includes(a.observation.word.state) && GUIDED_LEXICAL_STATES.includes(b.observation.word.state);
      const aa = attempts.find((v) => v.id === a.primaryAttemptId), bb = attempts.find((v) => v.id === b.primaryAttemptId);
      return { itemId, first: a, recheck: b, comparison: complete ? 'paired_observations' : 'no_comparison', sameAudioBytes: !!aa?.audioSha256 && aa.audioSha256 === bb?.audioSha256, independentAcousticEvidenceEstablished: false };
    });
    return guidedFreeze({ plannedPairs: 13, pairsWithTwoLexicalObservations: rows.filter((r) => r.comparison === 'paired_observations').length, rows });
  }

  // ---------- guided state pure end ----------

  const newSession = () => ({ recordings: 0, words: new Set() });

  const app = {
    prompts: [],
    promptById: new Map(),
    selectedId: null,
    catalogState: 'loading', // loading | ready | empty | error
    declaration: null,
    declarationState: 'loading', // loading | ready | error
    declarationGen: 0,
    practiceContext: null, // null or a frozen practiceContextCopy(); never a bare number
    optIn: false,
    setupGen: 0, // bumped whenever who is practicing, word check or a sound box is switched
    rec: { state: 'idle', message: '', elapsed: 0, level: 0 }, // idle | requesting | recording | finishing
    capture: null,
    captureGen: 0,
    takes: [], // oldest first, at most MAX_TAKES
    takeSeq: 0,
    results: new Map(), // take id -> result view; deleted with the take
    check: { state: 'idle' }, // idle | sending | stopped
    checkGen: 0,
    session: newSession(), // memory only; counts recordings kept, not results
    camera: { state: 'off', stream: null, message: '' }, // off | requesting | on
    cameraGen: 0,
    visual: { enabled: false, generation: 0, runtime: null, stopping: false, blocked: false, message: 'Face analysis is off.' },
    cleanupFailed: false,
    mode: 'free', // free | guided
    guided: null, // null or the frozen pure guided state; replaced only by accepted events
    guidedGen: 0, // session generations are never reused
    guidedNotice: '',
    guidedConfirming: false,
  };

  const playback = { example: 'idle', exampleMessage: '', takeId: null };
  let exampleGen = 0;
  let exampleSource = null;
  let exampleFetch = null;
  let exampleBlobUrl = null;
  let takePlayGen = 0;
  const exampleAudio = new Audio();
  exampleAudio.preload = 'none';
  // One player for both tries; its source is set when Play is chosen.
  const takeAudio = new Audio();
  takeAudio.preload = 'auto';

  const ui = {};
  const encoder = new TextEncoder();
  const cryptoReady = Boolean(window.isSecureContext && window.crypto && window.crypto.subtle);

  // ---------- small helpers ----------

  const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const str = (v) => (typeof v === 'string' ? v : '');
  const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const exactKeys = (obj, keys) => Object.keys(obj).length === keys.length && keys.every((k) => has(obj, k));
  const isHex = (v) => typeof v === 'string' && HEX64.test(v);
  const within = (v, low, high) => typeof v === 'number' && Number.isFinite(v) && v >= low && v <= high;
  // In guided mode the current guided item is the only word on screen.
  function currentPromptId() {
    if (app.mode !== 'guided') return app.selectedId;
    return app.guided ? app.guided.currentItemId : null;
  }
  const selectedPrompt = () => app.promptById.get(currentPromptId()) || null;
  const capturing = () => app.rec.state !== 'idle';
  const latestTake = () => app.takes[app.takes.length - 1] || null;
  const findTake = (id) => app.takes.find((t) => t.id === id) || null;
  const camel = (id) => id.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    if (props) {
      for (const key of Object.keys(props)) {
        const value = props[key];
        if (value === null || value === undefined || value === false) continue;
        if (key === 'text') node.textContent = String(value);
        else if (key === 'class') node.className = value;
        else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value === true ? '' : String(value));
      }
    }
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : String(child));
    }
    return node;
  }

  function uuid() {
    if (typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID().toLowerCase();
    const b = window.crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }

  // Same-origin path from a closed backend route; anything else is dropped.
  function safePath(value) {
    if (typeof value !== 'string' || !/^\/(?![/\\])/.test(value) || /[\s\\]/.test(value)) return null;
    try {
      const url = new URL(value, window.location.origin);
      return url.origin === window.location.origin ? url.pathname + url.search : null;
    } catch (_) {
      return null;
    }
  }

  // Only used for license and source page anchors.
  function safeExternal(value) {
    if (typeof value !== 'string') return null;
    try {
      const url = new URL(value);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function extLink(href, label) {
    return el('a', { href, target: '_blank', rel: 'noopener noreferrer' },
      label, el('span', { class: 'visually-hidden', text: ' (opens in a new tab)' }));
  }

  function fact(term, detail) {
    return [el('dt', { text: term }), el('dd', null, detail)];
  }

  function positionOf(id) {
    const token = String(id).split('-').find((part) => has(POSITION, part));
    return token ? POSITION[token] : '';
  }

  function announce(message) {
    ui.announcer.textContent = '';
    window.setTimeout(() => { ui.announcer.textContent = message; }, 50);
  }

  function seconds(value) {
    return `${value.toFixed(1)} s`;
  }

  function narrowScreen() {
    return typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 860px)').matches;
  }

  // ---------- hashing and canonical JSON ----------

  function compareCodePoints(a, b) {
    const x = Array.from(a);
    const y = Array.from(b);
    for (let i = 0; i < Math.min(x.length, y.length); i += 1) {
      const d = x[i].codePointAt(0) - y[i].codePointAt(0);
      if (d) return d;
    }
    return x.length - y.length;
  }

  // Matches the server's json.dumps(sort_keys=True, separators=(',', ':'),
  // ensure_ascii=False) for the values a prompt holds. Anything else throws.
  function canonicalJson(value) {
    if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
    if (typeof value === 'number') {
      if (!Number.isSafeInteger(value)) throw new Error('unsupported_number');
      return String(value);
    }
    if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
    if (isObj(value)) {
      const keys = Object.keys(value).sort(compareCodePoints);
      return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(',')}}`;
    }
    throw new Error('unsupported_value');
  }

  async function sha256Hex(bytes) {
    const digest = new Uint8Array(await window.crypto.subtle.digest('SHA-256', bytes));
    return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('');
  }

  function toBase64(bytes) {
    let binary = '';
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return window.btoa(binary);
  }

  // ---------- HTTP ----------

  async function getJson(path) {
    try {
      const res = await fetch(path, {
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) return null;
      return await res.json();
    } catch (_) {
      return null;
    }
  }

  async function readCapped(res, limit) {
    const declared = res.headers.get('Content-Length');
    if (declared !== null && !(/^\d+$/.test(declared) && Number(declared) <= limit)) throw new Error('too_large');
    if (!res.body) {
      const whole = new Uint8Array(await res.arrayBuffer());
      if (whole.length > limit) throw new Error('too_large');
      return whole;
    }
    const reader = res.body.getReader();
    const chunks = [];
    let total = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > limit) {
        reader.cancel().catch(() => {});
        throw new Error('too_large');
      }
      chunks.push(value);
    }
    const out = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      out.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return out;
  }

  // ---------- catalog ----------

  function normalizeReference(r) {
    if (!isObj(r)) return null;
    let changes = '';
    if (typeof r.changes === 'string') changes = r.changes;
    else if (Array.isArray(r.changes)) changes = r.changes.filter((c) => typeof c === 'string').join('; ');
    return {
      author: str(r.author),
      licenseId: str(r.licenseId),
      licenseUrl: safeExternal(r.licenseUrl),
      sourcePageUrl: safeExternal(r.sourcePageUrl),
      declaredVariety: str(r.declaredVariety),
      speakerAgeKnown: r.speakerAgeKnown === true,
      clinicalReferenceApproved: r.clinicalReferenceApproved === true,
      changes,
      attribution: str(r.attribution),
    };
  }

  // The processing prompt is sent back exactly as received. It is kept only if
  // it is a one-word schema 2 prompt for the word shown and can be hashed the
  // same way the server hashes it.
  function processingPromptOf(raw, word, sourceWord) {
    if (!isObj(raw) || raw.schemaVersion !== 2 || raw.language !== 'en') return null;
    if (!Array.isArray(raw.words) || raw.words.length !== 1 || !isObj(raw.words[0])) return null;
    if (!Array.isArray(raw.targets) || raw.targets.length === 0) return null;
    const text = str(raw.words[0].text).toLowerCase();
    if (!text || raw.transcript !== raw.words[0].text) return null;
    if (text !== word.toLowerCase() && text !== sourceWord.toLowerCase()) return null;
    try {
      canonicalJson(raw);
    } catch (_) {
      return null;
    }
    return raw;
  }

  function normalizePrompt(p) {
    if (!isObj(p) || typeof p.id !== 'string' || !p.id || typeof p.word !== 'string' || !p.word) return null;
    const sourceWord = str(p.sourceWord) || p.word;
    return {
      id: p.id,
      word: p.word,
      sourceWord,
      imageUrl: safePath(p.imageUrl),
      publicReferenceUrl: safePath(p.publicReferenceUrl),
      reference: normalizeReference(p.reference),
      processingPrompt: processingPromptOf(p.prompt, p.word, sourceWord),
    };
  }

  function normalizeCatalog(d) {
    if (!isObj(d) || d.schemaVersion !== 1 || !Array.isArray(d.prompts)) return null;
    if (!isObj(d.claimLimits) || Object.values(d.claimLimits).some((v) => v !== false)) return null;
    const seen = new Set();
    const prompts = [];
    for (const raw of d.prompts) {
      const p = normalizePrompt(raw);
      if (p && !seen.has(p.id)) {
        seen.add(p.id);
        prompts.push(p);
      }
    }
    return prompts;
  }

  async function loadCatalog() {
    const fromRetry = document.activeElement === ui.catalogRetry;
    app.catalogState = 'loading';
    renderWords();
    renderPractice();
    const prompts = normalizeCatalog(await getJson('/api/catalog'));
    if (!prompts) {
      app.catalogState = 'error';
    } else {
      app.prompts = prompts;
      app.promptById = new Map(prompts.map((p) => [p.id, p]));
      app.catalogState = prompts.length ? 'ready' : 'empty';
      if (!app.promptById.has(app.selectedId)) app.selectedId = prompts.length ? prompts[0].id : null;
    }
    renderWords();
    renderPractice();
    render();
    refreshGuidedContext();
    if (fromRetry) {
      const target = app.catalogState === 'ready' ? ui.wordList.querySelector('button.word-row') : ui.catalogRetry;
      if (target && !target.hidden) target.focus();
    }
  }

  // ---------- declaration ----------

  function normalizeDeclaration(d) {
    if (!isObj(d) || !exactKeys(d, DECLARATION_KEYS) || d.schemaVersion !== 1) return null;
    if (typeof d.csrfToken !== 'string' || !/^[\x21-\x7e]{1,512}$/.test(d.csrfToken)) return null;
    if (!isObj(d.pins) || !exactKeys(d.pins, PIN_KEYS) || !PIN_KEYS.every((k) => isHex(d.pins[k]))) return null;
    const policy = d.feedbackPolicy;
    if (!isObj(policy) || !exactKeys(policy, ['id', 'sha256']) || policy.id !== FEEDBACK_POLICY_ID || !isHex(policy.sha256)) return null;
    if (!FEEDBACK_HASH_KEYS.every((k) => isHex(d[k]))) return null;
    if (typeof d.processingAvailable !== 'boolean') return null;
    return Object.freeze({
      csrfToken: d.csrfToken,
      pins: Object.freeze(Object.fromEntries(PIN_KEYS.map((k) => [k, d.pins[k]]))),
      feedbackPolicySha256: policy.sha256,
      feedbackSourceSha256: d.feedbackSourceSha256,
      wrapperSourceSha256: d.wrapperSourceSha256,
      contentSha256: d.contentSha256,
      processingAvailable: d.processingAvailable,
    });
  }

  async function loadDeclaration() {
    const gen = ++app.declarationGen;
    // A check is bound to the declaration it was sent under.
    cancelCheck(STOPPED_TEXT);
    app.declarationState = 'loading';
    render();
    const declaration = normalizeDeclaration(await getJson(FEEDBACK_DECLARATION_PATH));
    if (gen !== app.declarationGen) return;
    app.declaration = declaration;
    app.declarationState = declaration ? 'ready' : 'error';
    if (!processingReady()) app.optIn = false;
    render();
    // A CSRF-only rotation keeps the guided session; any other change ends it.
    refreshGuidedContext();
    if (app.sound && app.sound.decl) {
      if (!declaration || !soundSource(app.sound.decl.binding,declaration)) {resetSound(true);clearTakes();render();}
      else app.sound.decl.csrfToken=declaration.csrfToken;
    }
  }

  // ---------- word selection ----------

  function renderWords() {
    ui.catalogRetry.hidden = app.catalogState !== 'error';
    if (app.catalogState !== 'ready') {
      ui.wordList.hidden = true;
      ui.wordList.replaceChildren();
      ui.wordStatus.hidden = false;
      ui.wordStatus.textContent = {
        loading: 'Loading words…',
        error: 'Words could not be loaded.',
        empty: 'No words are available right now.',
      }[app.catalogState];
      return;
    }
    ui.wordStatus.hidden = true;
    ui.wordStatus.textContent = '';
    ui.wordList.replaceChildren(...app.prompts.map((p) => {
      const pos = positionOf(p.id);
      return el('li', null,
        el('button', {
          type: 'button',
          class: 'word-row',
          'data-prompt': p.id,
          'aria-current': p.id === app.selectedId ? 'true' : null,
          onclick: () => selectPrompt(p.id),
        },
        el('span', { text: p.word }),
        pos ? el('span', { class: 'word-row-pos', text: `${pos} sound` }) : null));
    }));
    ui.wordList.hidden = false;
  }

  function onWordListKey(event) {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const buttons = Array.from(event.currentTarget.querySelectorAll('button.word-row'));
    const index = buttons.indexOf(document.activeElement);
    if (index === -1) return;
    event.preventDefault();
    let next = index;
    if (event.key === 'ArrowDown') next = Math.min(buttons.length - 1, index + 1);
    if (event.key === 'ArrowUp') next = Math.max(0, index - 1);
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = buttons.length - 1;
    buttons[next].focus();
  }

  function selectPrompt(id) {
    const prompt = app.promptById.get(id);
    if (!prompt || id === app.selectedId || app.mode !== 'free') return;
    resetSound(true);
    // Tries belong to one word. Changing word ends any capture and clears
    // both tries and their results; the camera mirror is not tied to a word.
    stopVisual();
    const hadTakes = app.takes.length > 0;
    cancelCapture('');
    clearTakes();
    app.rec = { state: 'idle', message: '', elapsed: 0, level: 0 };
    app.selectedId = id;
    for (const button of ui.wordList.querySelectorAll('button.word-row')) {
      if (button.dataset.prompt === id) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    }
    renderPractice();
    render();
    const cleared = hadTakes ? ' Tries for the last word were cleared.' : '';
    // On narrow screens the list sits below practice, so bring practice back
    // into view; focusing it already reads the new word.
    if (narrowScreen()) {
      ui.practice.focus();
      if (cleared) announce(cleared.trim());
      return;
    }
    const pos = positionOf(id);
    announce(`Showing ${prompt.word}${pos ? `, ${pos} sound` : ''}.${cleared}`);
  }

  function renderPractice() {
    const p = selectedPrompt();
    ui.reference.hidden = !p;
    if (!p) {
      ui.practiceBody.hidden = true;
      ui.practiceEmpty.hidden = false;
      ui.practiceMessage.textContent = {
        loading: 'Loading…',
        error: 'Practice words could not be loaded. Use Try again in the word list.',
        empty: 'No words are available right now.',
      }[app.catalogState] || '';
      setExampleSource(null);
      return;
    }
    ui.practiceEmpty.hidden = true;
    ui.practiceBody.hidden = false;
    ui.wordHeading.textContent = p.word;
    ui.recordWord.textContent = quote(p.word);
    const pos = positionOf(p.id);
    ui.wordPosition.textContent = pos ? `${pos.charAt(0).toUpperCase()}${pos.slice(1)} sound` : '';
    ui.wordPosition.hidden = !pos;
    const g = guidedItem();
    if (g) {
      ui.wordPosition.textContent = g.round
        ? `Word ${g.index + 1} of ${g.round.plannedItemIds.length}`
        : `Practice. Tries here don't change ${g.s.recheck ? "either round's" : 'the first-round'} results.`;
      ui.wordPosition.hidden = false;
    }

    if (p.imageUrl) {
      ui.picture.alt = `Picture of ${p.word}`;
      ui.picture.hidden = false;
      ui.pictureMissing.hidden = true;
      if (ui.picture.getAttribute('src') !== p.imageUrl) ui.picture.setAttribute('src', p.imageUrl);
    } else {
      ui.picture.removeAttribute('src');
      ui.picture.hidden = true;
      ui.pictureMissing.hidden = false;
    }

    setExampleSource(p.publicReferenceUrl);
    renderReference(p);
  }

  function renderReference(p) {
    const r = p.reference;
    if (!r) {
      ui.referenceDetails.replaceChildren(...fact('Details', 'Not available for this example.'));
      return;
    }
    const license = r.licenseUrl ? extLink(r.licenseUrl, r.licenseId || 'License terms') : (r.licenseId || 'Not stated');
    const rows = [
      ...fact('Recorded by', r.author || 'Not stated'),
      ...fact('License', license),
      ...fact('Source', r.sourcePageUrl ? extLink(r.sourcePageUrl, 'Original recording page') : 'Not stated'),
      ...fact('Changes', r.changes || 'None stated'),
      ...fact('Speaker age', r.speakerAgeKnown ? 'See the source page' : 'Not known'),
      ...fact('Accent or variety', r.declaredVariety || 'Not stated'),
      ...fact('Use', r.clinicalReferenceApproved ? 'Practice example.' : 'Practice example. Not a clinically approved reference.'),
    ];
    if (r.attribution) rows.push(...fact('Attribution', r.attribution));
    ui.referenceDetails.replaceChildren(...rows);
  }

  // ---------- example playback ----------

  function stopExample() {
    exampleGen += 1;
    if (exampleFetch) exampleFetch.abort();
    exampleFetch = null;
    playback.example = 'idle';
    exampleAudio.pause();
    try {
      exampleAudio.currentTime = 0;
    } catch (_) { /* not loaded yet */ }
    exampleAudio.removeAttribute('src');
    exampleAudio.load();
    if (exampleBlobUrl) URL.revokeObjectURL(exampleBlobUrl);
    exampleBlobUrl = null;
  }

  function setExampleSource(url) {
    stopExample();
    playback.exampleMessage = '';
    exampleSource = url || null;
    renderExample();
  }

  async function toggleExample() {
    if (playback.example !== 'idle') {
      stopExample();
      renderExample();
      return;
    }
    if (!exampleSource || capturing()) return;
    stopTake();
    const gen = ++exampleGen;
    const controller = new AbortController();
    exampleFetch = controller;
    const deadline = window.setTimeout(() => controller.abort(), 10000);
    playback.example = 'loading';
    playback.exampleMessage = '';
    render();
    try {
      // Media players request HTTP ranges; this closed local route serves full WAVs.
      // Fetch only after Play, bounded like the catalog, then play a short-lived blob.
      const res = await fetch(exampleSource, {
        credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        headers: { Accept: 'audio/wav' }, signal: controller.signal,
      });
      if (res.redirected || res.type !== 'basic' || res.status !== 200 ||
          !/^audio\/wav\s*(;|$)/i.test(res.headers.get('Content-Type') || '')) {
        if (res.body) res.body.cancel().catch(() => {});
        throw new Error('example_unavailable');
      }
      const bytes = await readCapped(res, MAX_AUDIO_BYTES);
      if (gen !== exampleGen) return;
      if (controller.signal.aborted) throw new Error('example_download_stopped');
      window.clearTimeout(deadline);
      if (!bytes.length) throw new Error('empty_example');
      exampleBlobUrl = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
      exampleAudio.src = exampleBlobUrl;
      await exampleAudio.play();
    } catch (_) {
      if (gen !== exampleGen) return;
      stopExample();
      playback.exampleMessage = 'The example could not be played. You can still record and practice.';
      renderExample();
    } finally {
      window.clearTimeout(deadline);
      if (exampleFetch === controller) exampleFetch = null;
    }
  }

  exampleAudio.addEventListener('playing', () => {
    if (playback.example === 'idle' || !exampleBlobUrl || exampleAudio.currentSrc !== exampleBlobUrl) return;
    playback.example = 'playing';
    renderExample();
  });
  exampleAudio.addEventListener('ended', () => { stopExample(); renderExample(); });
  // Covers pauses from outside the page, such as hardware media keys.
  exampleAudio.addEventListener('pause', () => {
    if (playback.example !== 'playing') return;
    stopExample();
    renderExample();
  });
  exampleAudio.addEventListener('error', () => {
    if (playback.example === 'idle' || !exampleBlobUrl) return;
    stopExample();
    playback.exampleMessage = 'The example could not be played. You can still record and practice.';
    renderExample();
  });

  function renderExample() {
    const hasSource = Boolean(exampleSource);
    for (const button of [ui.examplePlay, ui.compareExample, ui.brExample]) {
      button.textContent = playback.example === 'idle' ? 'Play example' : 'Stop example';
      button.disabled = !hasSource || capturing();
    }
    let message = playback.exampleMessage;
    if (!hasSource) message = 'No example recording for this word. You can still record and practice.';
    else if (playback.example === 'loading') message = 'Loading the example…';
    ui.exampleStatus.textContent = message;
  }

  // ---------- recording ----------

  function captureSupported() {
    return Boolean(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
      window.AudioContext && window.AudioWorkletNode && window.OfflineAudioContext);
  }

  function mediaErrorText(err, kind) {
    const Kind = kind.charAt(0).toUpperCase() + kind.slice(1);
    const name = err && err.name;
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      return `${Kind} access was blocked. Allow it for this page in the browser's site settings, then try again.`;
    }
    if (name === 'NotFoundError' || name === 'OverconstrainedError') return `No ${kind} was found. Connect one, then try again.`;
    if (name === 'NotReadableError' || name === 'AbortError') {
      return `The ${kind} is busy or could not start. Close other apps that might be using it, then try again.`;
    }
    return `The ${kind} could not start. Try again.`;
  }

  function stopStream(stream) {
    if (!stream) return true;
    let ok = true;
    for (const track of stream.getTracks()) {
      try {
        track.stop();
      } catch (_) {
        ok = false;
      }
      if (track.readyState !== 'ended') ok = false;
    }
    return ok;
  }

  function reportCleanupFailure() {
    if (app.cleanupFailed) return;
    app.cleanupFailed = true;
    render();
    announce('The microphone or camera may not have turned off properly. Reload the page before recording again.');
  }

  const stale = (cap) => cap.gen !== app.captureGen;

  // Releases everything a capture holds. Safe to call more than once and on a
  // partly built capture. Tracks stop synchronously; the promise reports
  // whether the audio context also closed.
  function releaseCapture(cap) {
    for (const timer of cap.timers) window.clearTimeout(timer);
    cap.timers = [];
    const tracksStopped = stopStream(cap.stream);
    cap.stream = null;
    if (cap.node) {
      cap.node.port.onmessage = null;
      try {
        cap.node.port.close();
      } catch (_) { /* already closed */ }
    }
    for (const node of cap.nodes) {
      try {
        node.disconnect();
      } catch (_) { /* already disconnected */ }
    }
    cap.nodes = [];
    cap.node = null;
    const context = cap.context;
    cap.context = null;
    if (!tracksStopped) reportCleanupFailure();
    if (!context || context.state === 'closed') return Promise.resolve(tracksStopped);
    context.onstatechange = null;
    return context.close().then(() => tracksStopped, () => {
      reportCleanupFailure();
      return false;
    });
  }

  // Settles a guided capture's attempt once, before it has a take. The pure
  // state refuses it when navigation or a reset already closed the attempt.
  function guidedCaptureTerminal(cap, code) {
    const owner = cap.guidedOwner;
    cap.guidedOwner = null;
    if (owner) guidedApply({ type: 'attempt_terminal', owner, code });
  }

  function cancelCapture(message, code = 'capture_cancelled') {
    const cap = app.capture;
    app.captureGen += 1;
    app.capture = null;
    if (cap) {
      releaseCapture(cap);
      guidedCaptureTerminal(cap, code);
    }
    if (cap || message) app.rec = { state: 'idle', message: message || '', elapsed: 0, level: 0 };
  }

  function failCapture(cap, message, code = 'capture_failed') {
    if (stale(cap)) {
      releaseCapture(cap);
      return;
    }
    app.captureGen += 1;
    app.capture = null;
    releaseCapture(cap);
    guidedCaptureTerminal(cap, code);
    app.rec = { state: 'idle', message, elapsed: 0, level: 0 };
    render();
  }

  async function startRecording() {
    const prompt = selectedPrompt();
    if (!prompt || app.cleanupFailed || capturing()) return;
    resetSound(false,app.sound.check.state==='sending'?'The comparison stopped when a new recording started. No result will be shown for it.':'');
    // A guided Record starts its bounded attempt before any permission request.
    let owner = null;
    if (app.mode === 'guided') {
      const g = guidedItem();
      if (!g || !g.recordAllowed) {
        render();
        return;
      }
      const r = guidedApply({ type: 'record_start', attemptId: uuid(), captureId: uuid() });
      if (!r || !r.accepted) {
        app.rec = { state: 'idle', message: r && r.reason === 'attempt_limit' ? GUIDED_LIMIT_TEXT : 'Recording could not start. Try again.', elapsed: 0, level: 0 };
        render();
        return;
      }
      owner = r.actions.find((a) => a.type === 'start_capture').owner;
    }
    stopExample();
    stopTake();
    if (!captureSupported()) {
      app.rec = { state: 'idle', message: 'This browser cannot record here. Open the page from this computer (localhost) in a current browser.', elapsed: 0, level: 0 };
      if (owner) guidedApply({ type: 'attempt_terminal', owner, code: 'capture_failed' });
      render();
      return;
    }
    // Earlier tries stay until the new one is kept, but a running check stops:
    // its result could otherwise land while a different try is on screen.
    cancelCheck(NEW_RECORDING_STOPPED_TEXT);

    const cap = {
      gen: ++app.captureGen,
      promptId: prompt.id,
      setupGen: app.setupGen,
      practiceContext: practiceContextCopy(app.practiceContext), // null still records
      stream: null,
      context: null,
      nodes: [],
      node: null,
      rate: 0,
      maxFrames: 0,
      timers: [],
      finishing: false,
      done: false,
      guidedOwner: owner, // null-take owner; handed to the take on capture_ready
      awaitingPermission: false,
    };
    app.capture = cap;
    app.rec = { state: 'requesting', message: '', elapsed: 0, level: 0 };
    render();

    // The audio context is created inside the tap so the browser lets it run.
    try {
      cap.context = new AudioContext({ latencyHint: 'interactive' });
      cap.context.resume().catch(() => {});
    } catch (_) {
      failCapture(cap, 'This browser could not start audio recording. Try again.');
      return;
    }
    cap.rate = cap.context.sampleRate;
    if (!Number.isFinite(cap.rate) || cap.rate < MIN_INPUT_RATE || cap.rate > MAX_INPUT_RATE) {
      failCapture(cap, `This computer's audio rate (${Math.round(cap.rate)} Hz) is not supported for recording here.`);
      return;
    }
    cap.maxFrames = Math.ceil(cap.rate * MAX_SECONDS);

    let stream;
    cap.awaitingPermission = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: { ideal: 1 }, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
        video: false,
      });
    } catch (err) {
      cap.awaitingPermission = false;
      const name = err && err.name;
      failCapture(cap, mediaErrorText(err, 'microphone'),
        name === 'NotAllowedError' || name === 'SecurityError' ? 'permission_denied' : 'capture_failed');
      return;
    }
    cap.awaitingPermission = false;
    cap.stream = stream;
    if (stale(cap)) {
      releaseCapture(cap);
      return;
    }

    try {
      await cap.context.audioWorklet.addModule('audio-capture.js');
      if (stale(cap)) {
        releaseCapture(cap);
        return;
      }
      const source = cap.context.createMediaStreamSource(stream);
      cap.nodes.push(source);
      let tail = source;
      // Two biquads form a 4th-order low-pass ahead of downsampling to 16 kHz.
      if (cap.rate > TARGET_RATE) {
        for (const q of [0.5412, 1.3066]) {
          const filter = new BiquadFilterNode(cap.context, { type: 'lowpass', frequency: ANTI_ALIAS_HZ, Q: q });
          cap.nodes.push(filter);
          tail.connect(filter);
          tail = filter;
        }
      }
      const node = new AudioWorkletNode(cap.context, 'bounded-capture', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        processorOptions: { maxFrames: cap.maxFrames },
      });
      node.port.onmessage = (event) => onCaptureMessage(cap, event.data);
      cap.node = node;
      cap.nodes.push(node);
      tail.connect(node);
      // The processor writes silence; the connection keeps it rendering.
      node.connect(cap.context.destination);
      if (cap.context.state !== 'running') await cap.context.resume();
      if (stale(cap)) {
        releaseCapture(cap);
        return;
      }
      if (cap.context.state !== 'running') throw new Error('not_running');
    } catch (_) {
      failCapture(cap, 'The microphone could not start recording. Try again.');
      return;
    }

    for (const track of stream.getAudioTracks()) track.addEventListener('ended', () => requestFinish(cap));
    cap.context.onstatechange = () => {
      if (cap.context && cap.context.state !== 'running') requestFinish(cap);
    };
    cap.timers.push(window.setTimeout(() => requestFinish(cap), MAX_SECONDS * 1000 + SAFETY_MARGIN_MS));
    app.rec = { state: 'recording', message: '', elapsed: 0, level: 0 };
    render();
  }

  function onCaptureMessage(cap, msg) {
    if (stale(cap) || !isObj(msg)) return;
    if (msg.type === 'level') {
      if (cap.finishing || !Number.isFinite(msg.peak) || !Number.isInteger(msg.frames)) return;
      app.rec.level = Math.max(0, Math.min(1, msg.peak));
      app.rec.elapsed = Math.max(0, Math.min(MAX_SECONDS, msg.frames / cap.rate));
      renderMeters();
    } else if (msg.type === 'data') {
      completeCapture(cap, msg);
    }
  }

  // Stop asks the processor for what it has; a full buffer arrives on its own.
  function requestFinish(cap) {
    if (stale(cap) || cap.finishing || app.rec.state !== 'recording') return;
    cap.finishing = true;
    app.rec.state = 'finishing';
    app.rec.level = 0;
    render();
    try {
      cap.node.port.postMessage('finish');
    } catch (_) {
      completeCapture(cap, null);
      return;
    }
    cap.timers.push(window.setTimeout(() => completeCapture(cap, null), FINISH_WAIT_MS));
  }

  function capturedSamples(cap, msg) {
    if (!isObj(msg) || !(msg.buffer instanceof ArrayBuffer) || msg.sampleRate !== cap.rate) return null;
    const length = msg.length;
    if (!Number.isInteger(length) || length <= 0 || length > cap.maxFrames || length * 4 > msg.buffer.byteLength) return null;
    return new Float32Array(msg.buffer, 0, length);
  }

  async function completeCapture(cap, msg) {
    if (stale(cap) || cap.done) return;
    cap.done = true;
    cap.finishing = true;
    if (app.rec.state !== 'finishing') {
      app.rec.state = 'finishing';
      app.rec.level = 0;
      render();
    }
    const samples = capturedSamples(cap, msg);
    const released = await releaseCapture(cap);
    if (stale(cap)) return;
    if (!released) {
      finishWithMessage(cap, 'The recording was not kept because the microphone may not have turned off properly.');
      return;
    }
    if (!samples) {
      finishWithMessage(cap, 'No sound was captured. Check that the microphone is connected and not muted, then try again.');
      return;
    }
    let result;
    try {
      result = await encodeTake(samples, cap.rate);
    } catch (err) {
      if (stale(cap)) return;
      finishWithMessage(cap, err && err.message === 'too_short'
        ? 'That was too short to keep. Tap Record, say the word, then tap Stop.'
        : 'The recording could not be prepared. Try again.');
      return;
    }
    if (stale(cap)) {
      result.wav.fill(0);
      return;
    }
    // A guided take is installed only after its digest exists and the original
    // owner still holds. The capture stays current while hashing.
    let guided = null;
    if (cap.guidedOwner) {
      let audioSha256 = null;
      try {
        audioSha256 = await sha256Hex(result.wav);
      } catch (_) { /* reported below */ }
      if (stale(cap)) {
        result.wav.fill(0);
        return;
      }
      if (!audioSha256 || !guidedOwns(app.guided, cap.guidedOwner)) {
        result.wav.fill(0);
        finishWithMessage(cap, audioSha256 ? '' : 'The recording could not be prepared. Try again.');
        return;
      }
      const seq = ++app.takeSeq;
      const takeId = `take-${seq}`;
      const r = guidedApply({ type: 'capture_ready', owner: cap.guidedOwner, takeId, audioSha256 });
      if (!r || !r.accepted) {
        result.wav.fill(0);
        finishWithMessage(cap, 'The recording could not be kept. Try again.');
        return;
      }
      // The owner now carries the take ID; the capture no longer owns the attempt.
      guided = { seq, owner: guidedOwner(app.guided, cap.guidedOwner.attemptId) };
      cap.guidedOwner = null;
    }
    app.capture = null;
    const dropped = addTake(result.wav, result.sampleCount, cap.promptId, cap.setupGen, cap.practiceContext, guided);
    app.rec = { state: 'idle', message: '', elapsed: result.sampleCount / TARGET_RATE, level: 0 };
    render();
    const next = checkableTake() ? 'Choose Check this try when you are ready.' : 'You can play it back or record again.';
    announce(`Recorded ${seconds(result.sampleCount / TARGET_RATE)}. ${next}${dropped ? ' Your oldest try was removed; the last two are kept.' : ''}`);
    // Every kept take waits for its own Check action.
  }

  function finishWithMessage(cap, message) {
    guidedCaptureTerminal(cap, 'capture_failed');
    app.capture = null;
    app.rec = { state: 'idle', message, elapsed: 0, level: 0 };
    render();
  }

  // Downsamples with an OfflineAudioContext, keeps at most 4 seconds at
  // 16 kHz and encodes PCM16 mono WAV.
  async function encodeTake(samples, rate) {
    const outLength = Math.min(MAX_SAMPLES, Math.floor(samples.length * TARGET_RATE / rate));
    if (outLength < MIN_SAMPLES) throw new Error('too_short');
    let pcm;
    if (rate === TARGET_RATE) {
      pcm = samples.subarray(0, outLength);
    } else {
      const offline = new OfflineAudioContext(1, outLength, TARGET_RATE);
      const buffer = offline.createBuffer(1, samples.length, rate);
      buffer.copyToChannel(samples, 0);
      const source = offline.createBufferSource();
      source.buffer = buffer;
      source.connect(offline.destination);
      source.start(0);
      const rendered = await offline.startRendering();
      source.disconnect();
      pcm = rendered.getChannelData(0);
    }
    return { wav: encodeWav(pcm), sampleCount: pcm.length };
  }

  function encodeWav(pcm) {
    const dataBytes = pcm.length * 2;
    const bytes = new Uint8Array(44 + dataBytes);
    const view = new DataView(bytes.buffer);
    const ascii = (offset, text) => {
      for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
    };
    ascii(0, 'RIFF');
    view.setUint32(4, 36 + dataBytes, true);
    ascii(8, 'WAVE');
    ascii(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, TARGET_RATE, true);
    view.setUint32(28, TARGET_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    ascii(36, 'data');
    view.setUint32(40, dataBytes, true);
    for (let i = 0; i < pcm.length; i += 1) {
      let s = pcm[i];
      if (s > 1) s = 1;
      else if (s < -1) s = -1;
      else if (s !== s) s = 0;
      view.setInt16(44 + i * 2, s < 0 ? Math.round(s * 32768) : Math.round(s * 32767), true);
    }
    return bytes;
  }

  function onRecordClick() {
    if (app.rec.state === 'recording') {
      if (app.capture) requestFinish(app.capture);
      return;
    }
    startRecording();
  }

  function onRecordCancel() {
    if (app.rec.state !== 'requesting') return;
    const code = app.capture && app.capture.awaitingPermission ? 'permission_cancelled' : 'capture_cancelled';
    cancelCapture('Cancelled. Nothing was recorded.', code);
    render();
    ui.record.focus();
  }

  // ---------- the tries held in this tab ----------

  // Keeps the new take; the oldest goes only once a third one is kept.
  // A guided take already has its sequence number and its take-bearing owner.
  // The practice context is the one in force when Record was chosen; both the
  // word check and the sound comparison compare it with the live choice.
  function addTake(wav, sampleCount, promptId, setupGen, practiceContext, guided = null) {
    resetSound();
    const url = URL.createObjectURL(new Blob([wav], { type: 'audio/wav' }));
    const take = { id: guided ? guided.seq : ++app.takeSeq, wav, url, sampleCount, promptId, setupGen, practiceContext: practiceContextCopy(practiceContext), soundCaptureId:cryptoReady?uuid():null, soundChecked:false };
    if (guided) {
      take.guidedOwner = guided.owner;
      take.guidedChecked = false; // one Check per guided take, practice included
    } else {
      app.session.recordings += 1;
      app.session.words.add(promptId);
    }
    app.takes.push(take);
    let dropped = false;
    while (app.takes.length > MAX_TAKES) {
      dropTake(app.takes[0]);
      dropped = true;
    }
    return dropped;
  }

  // Removes one take with everything bound to it: its check, its result,
  // its playback, its object URL and its bytes.
  function dropTake(take) {
    if ((app.sound.check.takeId===take.id) || (app.sound.result && app.sound.result.takeId===take.id)) resetSound();
    if (app.check.state === 'sending' && app.check.takeId === take.id) cancelCheck(STOPPED_TEXT);
    // An unsubmitted guided take is settled before its bytes go; the pure
    // state refuses this for submitted or already closed attempts.
    if (take.guidedOwner) {
      guidedApply({ type: 'attempt_terminal', owner: take.guidedOwner, code: 'recorded_discarded' });
      take.guidedOwner = null;
    }
    if (playback.takeId === take.id) stopTake();
    if (takeAudio.getAttribute('src') === take.url) {
      takeAudio.removeAttribute('src');
      takeAudio.load();
    }
    app.takes = app.takes.filter((t) => t !== take);
    app.results.delete(take.id);
    URL.revokeObjectURL(take.url);
    take.wav.fill(0);
  }

  function clearTakes() {
    resetSound();
    cancelCheck(STOPPED_TEXT);
    stopTake();
    for (const take of app.takes.slice()) dropTake(take);
    app.check = { state: 'idle' };
  }

  function stopTake() {
    takePlayGen += 1;
    takeAudio.pause();
    try {
      takeAudio.currentTime = 0;
    } catch (_) { /* not loaded yet */ }
    playback.takeId = null;
  }

  async function toggleTake(id) {
    if (playback.takeId === id) {
      stopTake();
      renderCompare();
      return;
    }
    const take = findTake(id);
    if (!take || capturing()) return;
    stopExample();
    stopTake();
    if (takeAudio.getAttribute('src') !== take.url) takeAudio.src = take.url;
    const gen = ++takePlayGen;
    playback.takeId = id;
    render();
    try {
      await takeAudio.play();
    } catch (_) {
      if (gen !== takePlayGen) return;
      playback.takeId = null;
      app.rec.message = 'That try could not be played. Try recording again.';
      render();
    }
  }

  takeAudio.addEventListener('ended', () => { stopTake(); renderCompare(); });
  // A pause queued while switching tries arrives after the new play() and is ignored.
  takeAudio.addEventListener('pause', () => {
    if (playback.takeId === null || takeAudio.ended || !takeAudio.paused) return;
    stopTake();
    renderCompare();
  });
  takeAudio.addEventListener('error', () => {
    if (playback.takeId === null) return;
    stopTake();
    app.rec.message = 'That try could not be played. Try recording again.';
    render();
  });

  function onClearTakes() {
    if (!app.takes.length || capturing()) return;
    stopVisual();
    clearTakes();
    app.rec = { state: 'idle', message: 'Tries cleared.', elapsed: 0, level: 0 };
    render();
    ui.record.focus();
  }

  // ---------- word check ----------

  function processingReady() {
    if (app.sound && app.sound.paused) return false;
    return app.declarationState === 'ready' && app.declaration.processingAvailable && cryptoReady;
  }

  // Null when the selected word can be checked; otherwise what to show instead.
  function checkBlocker(prompt) {
    if (app.sound.paused) return {title:'Word check is paused',text:'Processing is paused on this computer until cleanup is checked. You can still record and listen.'};
    if (app.declarationState === 'loading') return { title: '', text: 'Checking whether word check is available…' };
    if (app.declarationState === 'error') return { title: 'Word check could not be set up', text: CAN_STILL, setupRetry: true };
    if (!app.declaration.processingAvailable) {
      return { title: 'Word check is not available', text: `It is not available on this computer right now. ${CAN_STILL}` };
    }
    if (!cryptoReady) {
      return { title: 'Word check is not available', text: `This browser cannot prepare recordings for word check on this page. ${CAN_STILL}` };
    }
    if (!prompt) return { title: '', text: '' };
    if (!prompt.processingPrompt) return { title: 'Word check does not cover this word', text: CAN_STILL };
    return null;
  }

  // The latest take, when it may be sent now: recorded for this word under the
  // current settings and practice context, and with no result yet or only a
  // failure that observed nothing.
  function checkableTake() {
    const take = latestTake();
    const prompt = selectedPrompt();
    if (!take || !prompt || capturing() || app.check.state === 'sending' || app.sound.check.state === 'sending' || app.sound.paused) return null;
    if (!app.optIn || !practiceContextValid(app.practiceContext) || !processingReady() || checkBlocker(prompt) !== null) return null;
    if (take.promptId !== prompt.id || take.setupGen !== app.setupGen || !practiceContextSame(take.practiceContext, app.practiceContext)) return null;
    const result = app.results.get(take.id);
    if (app.mode === 'guided') {
      // Guided: never a retry on the same take, and never after the round word closed.
      const g = guidedItem();
      if (!g || g.closed || result || !take.guidedOwner || take.guidedChecked || !guidedOwns(app.guided, take.guidedOwner)) return null;
      if (!practiceContextSame(take.practiceContext, app.guided.context.practiceContext)) return null;
      return take;
    }
    return !result || result.retry ? take : null;
  }

  function cancelCheck(stoppedText) {
    const check = app.check;
    if (check.state !== 'sending') return false;
    app.checkGen += 1;
    check.controller.abort();
    app.check = { state: 'stopped', takeId: check.takeId, text: stoppedText || STOPPED_TEXT };
    if (check.guidedOwner) guidedApply({ type: 'attempt_terminal', owner: check.guidedOwner, code: 'check_cancelled' });
    return true;
  }

  async function startCheck() {
    const take = checkableTake();
    const prompt = selectedPrompt();
    // Only the take the button was drawn for is ever sent.
    if (!take || ui.fbCheck.dataset.take !== String(take.id)) return;
    // A guided Check closes the round word at once, before any preparation.
    let guided = null;
    if (take.guidedOwner) {
      const r = guidedApply({ type: 'check', owner: take.guidedOwner });
      if (!r || !r.accepted) {
        render();
        return;
      }
      take.guidedChecked = true;
      guided = { owner: r.actions.find((a) => a.type === 'submit_check').owner };
    }
    const gen = ++app.checkGen;
    const setupGen = app.setupGen;
    // The request carries the take's own context, already equal to the live one.
    const practiceContext = practiceContextCopy(take.practiceContext);
    const controller = new AbortController();
    app.check = { state: 'sending', takeId: take.id, controller, guidedOwner: guided ? guided.owner : null };
    if (guided) {
      // The fingerprint is the one fixed when Check was chosen, never the live app state.
      guided.fingerprint = guided.owner.fingerprint;
      // One POST per take: the pure gate must accept immediately before fetch.
      guided.beforePost = () => {
        if (gen !== app.checkGen || !guidedOwns(app.guided, guided.owner)) return false;
        const r = guidedApply({ type: 'post_started', owner: guided.owner });
        return Boolean(r && r.accepted);
      };
    }
    const moveFocus = document.activeElement === ui.fbCheck;
    render();
    if (moveFocus) ui.fbCancel.focus();
    announce('Checking this try.');
    let view;
    try {
      view = await sendForFeedback(take, prompt, practiceContext, app.declaration, controller.signal, guided);
    } catch (_) {
      if (gen !== app.checkGen) return;
      view = failureView(OUTCOME.unreachable, null, null, prompt.word);
    }
    if (gen !== app.checkGen) return;
    app.check = { state: 'idle' };
    if (guided) {
      view = settleGuidedCheck(guided.owner, view, prompt.word);
      if (!view) {
        render();
        return;
      }
    }
    // The reply belongs to this take only, while it is still held for the same
    // word, settings and practice context.
    if (findTake(take.id) !== take || take.promptId !== currentPromptId() || setupGen !== app.setupGen ||
        !practiceContextSame(practiceContext, app.practiceContext)) {
      render();
      return;
    }
    app.results.set(take.id, view);
    if (view.refresh) loadDeclaration();
    const focusResult = document.activeElement === ui.fbCancel || document.activeElement === document.body;
    render();
    if (focusResult) ui.fbResult.focus();
    else announce(view.title);
  }

  // `guided` is null in free practice; otherwise { fingerprint, beforePost }.
  // `practiceContext` is sent exactly as the closed object; nothing stands in for it.
  async function sendForFeedback(take, prompt, practiceContext, declaration, signal, guided = null) {
    const failed = (outcome) => {
      const view = failureView(outcome, null, null, prompt.word);
      // Bounded local terminal for a guided check; no reply content is kept.
      if (guided) view.localCode = outcome === OUTCOME.invalid ? 'invalid_response' : 'check_failed';
      return view;
    };
    const declared = practiceContextCopy(practiceContext);
    if (!declared) return failed(OUTCOME.rejected);
    const attemptId = uuid();
    const body = {
      schemaVersion: 2,
      attemptId,
      practiceContext: declared,
      prompt: prompt.processingPrompt,
      audioBase64: toBase64(take.wav),
    };
    // requestSha256 below hashes exactly these bytes, so it binds the context too.
    const raw = encoder.encode(JSON.stringify(body));
    if (take.wav.length > MAX_AUDIO_BYTES || raw.length > MAX_REQUEST_BYTES) return failureView(OUTCOME.tooLarge, null, null, prompt.word);
    const expected = Object.assign({
      attemptId,
      requestSha256: await sha256Hex(raw),
      audioSha256: await sha256Hex(take.wav),
      promptSha256: await sha256Hex(encoder.encode(canonicalJson(prompt.processingPrompt))),
      feedbackPolicySha256: declaration.feedbackPolicySha256,
    }, Object.fromEntries(FEEDBACK_PIN_KEYS.map((k) => [k, declaration.pins[k]])),
    Object.fromEntries(FEEDBACK_HASH_KEYS.map((k) => [k, declaration[k]])));
    const context = {
      word: prompt.word,
      sampleCount: take.sampleCount,
      zh: prompt.processingPrompt.targets.some((t) => isObj(t) && t.targetPhone === 'ZH'),
    };
    if (guided) context.fingerprint = guided.fingerprint;

    if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
    // After the hashing awaits, the live choice must still equal the snapshot.
    // A change normally aborts first; this refuses the POST if it did not.
    if (!practiceContextSame(declared, app.practiceContext)) throw new Error('context_changed');
    if (guided && !guided.beforePost()) throw new Error('post_refused');

    let res;
    try {
      res = await fetch(FEEDBACK_PATH, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          [CSRF_HEADER]: declaration.csrfToken,
        },
        body: raw,
        signal,
      });
    } catch (err) {
      if (signal.aborted) throw err;
      return failed(OUTCOME.unreachable);
    }
    if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
    if (res.redirected || res.type !== 'basic') return failed(OUTCOME.invalid);
    if (res.status !== 200) {
      if (res.body) res.body.cancel().catch(() => {});
      // The caller refreshes the declaration, and only while this check is current.
      if (res.status === 401 || res.status === 403) return failed(OUTCOME.session);
      if (res.status === 400) return failed(OUTCOME.rejected);
      if (res.status === 409 || res.status === 429) return failed(OUTCOME.busy);
      if (res.status === 503) return failed(OUTCOME.failed);
      return failed(OUTCOME.unreachable);
    }
    if (!/^application\/json\s*(;|$)/i.test(res.headers.get('Content-Type') || '')) return failed(OUTCOME.invalid);
    let data;
    try {
      const bytes = await readCapped(res, MAX_RESPONSE_BYTES);
      data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    } catch (err) {
      if (signal.aborted) throw err;
      return failed(OUTCOME.invalid);
    }
    return interpretFeedback(data, expected, context);
  }

  // What a reason code requires of the rest of the reply. Null for unknown codes.
  function stageRule(reason) {
    if (reason === null) {
      return { status: 'observed', speech: ['model_detected', null], word: ['model_matched', null], evidence: true, capture: 'observed', rails: 'none', rms: 'normal' };
    }
    if (typeof reason !== 'string') return null;
    if (has(WORD_STATE, reason)) {
      return { status: 'observed', speech: ['model_detected', null], word: [WORD_STATE[reason], reason], evidence: true, capture: 'observed', rails: 'none', rms: 'normal' };
    }
    if (reason === 'speech_not_detected') {
      return { status: 'observed', speech: ['model_not_detected', reason], word: ['not_run', reason], evidence: true, capture: 'observed', rails: 'none', rms: 'normal' };
    }
    if (reason === 'silence' || reason === 'clipping') {
      return { status: 'observed', speech: ['not_run', reason], word: ['not_run', reason], evidence: true, capture: 'observed', rails: reason === 'clipping' ? 'some' : 'none', rms: reason === 'silence' ? 'quiet' : null };
    }
    if (reason === 'invalid_audio') {
      return { status: 'unavailable', speech: ['not_run', reason], word: ['not_run', reason], evidence: true, capture: 'invalid' };
    }
    if (MODEL_FAILURES.includes(reason)) {
      return { status: 'unavailable', speech: ['unavailable', reason], word: ['unavailable', reason], evidence: true, capture: 'observed', rails: 'none', rms: 'normal' };
    }
    if (SERVICE_FAILURES.includes(reason)) {
      // The service withholds recording details when its cleanup is unconfirmed.
      return { status: 'unavailable', speech: ['unavailable', reason], word: ['unavailable', reason], evidence: false, capture: reason === 'cleanup_unconfirmed' ? 'withheld' : 'any' };
    }
    return null;
  }

  const stageIs = (v, [state, reason]) => isObj(v) && exactKeys(v, STAGE_KEYS) && v.state === state && v.reason === reason;

  // Recording properties must be finite, in range, consistent with each other,
  // and describe the same number of samples this page sent.
  function captureMatches(c, rule, sampleCount) {
    if (!isObj(c) || !exactKeys(c, CAPTURE_KEYS)) return false;
    if (c.state === 'unavailable') {
      if (!METRIC_KEYS.every((k) => c[k] === null)) return false;
      if (rule.capture === 'withheld') return c.reason === 'cleanup_unconfirmed';
      return (rule.capture === 'invalid' || rule.capture === 'any') && c.reason === 'invalid_audio';
    }
    if (c.state !== 'observed' || c.reason !== null || (rule.capture !== 'observed' && rule.capture !== 'any')) return false;
    const n = c.sampleCount;
    const rails = c.railSamples;
    if (!Number.isInteger(n) || n < MIN_SAMPLES || n > MAX_SAMPLES || n !== sampleCount || !Number.isInteger(rails) || rails < 0 || rails > n) return false;
    if (!within(c.durationMilliseconds, 0, MAX_SECONDS * 1000) || Math.abs(c.durationMilliseconds - n / 16) > 1e-6) return false;
    if (!within(c.rms, 0, 1) || !within(c.peak, 0, 1) || c.rms > c.peak + 1e-12) return false;
    if (!within(c.clippedFraction, 0, 1) || Math.abs(c.clippedFraction - rails / n) > 1e-12) return false;
    const dbfs = c.rms === 0 ? -120 : Math.max(-120, 20 * Math.log10(c.rms));
    if (!within(c.rmsDbfs, -120, 0) || Math.abs(c.rmsDbfs - dbfs) > 1e-9) return false;
    if (rule.rms === 'normal' && c.rms < POLICY_MIN_RMS) return false;
    if (rule.rms === 'quiet' && c.rms >= POLICY_MIN_RMS) return false;
    if (rule.rails === 'none' && rails !== 0) return false;
    if (rule.rails === 'some' && rails === 0) return false;
    return true;
  }

  // Known, unique, at most three, and none that contradicts the outcome.
  function suggestionsMatch(codes, d) {
    if (!Array.isArray(codes) || codes.length > 3 || new Set(codes).size !== codes.length) return false;
    const word = d.stages.word.state;
    return codes.every((code) => {
      if (typeof code !== 'string' || !has(SUGGESTIONS, code)) return false;
      if (code === 'continue_practice') return word === 'model_matched';
      if (code === 'reduce_recording_level') return d.reason === 'clipping';
      if (code === 'say_one_word') return ['model_not_matched', 'not_single_word', 'uncertain'].includes(word);
      if (code === 'retry_later' || code === 'processing_unavailable') return d.status === 'unavailable';
      return true;
    });
  }

  // Accepts only the exact reply shape, bound to this request, this recording,
  // this prompt and the declaration it was sent under, with every stage
  // consistent with the reason. Anything else shows no result.
  function interpretFeedback(d, expected, context) {
    const invalid = failureView(OUTCOME.invalid, null, null, context.word);
    // A guided check settles an invalid reply locally; it never gets an observation.
    if (typeof context.fingerprint === 'string') invalid.localCode = 'invalid_response';
    if (!isObj(d) || !exactKeys(d, RESPONSE_KEYS) || d.schemaVersion !== 1 || d.kind !== 'recording_feedback') return invalid;
    if (!isObj(d.claimLimits) || !exactKeys(d.claimLimits, CLAIM_KEYS) || !CLAIM_KEYS.every((k) => d.claimLimits[k] === false)) {
      return invalid;
    }
    if (typeof d.elapsedMilliseconds !== 'number' || !Number.isFinite(d.elapsedMilliseconds) || d.elapsedMilliseconds < 0) {
      return invalid;
    }
    const b = d.binding;
    if (!isObj(b) || !exactKeys(b, BINDING_KEYS) || !BOUND_KEYS.every((k) => b[k] === expected[k])) return invalid;
    const rule = stageRule(d.reason);
    if (!rule || d.status !== rule.status) return invalid;
    // The evidence digest is only checked for form; the page has nothing to compare it with.
    if (rule.evidence ? !isHex(b.evidenceSha256) : b.evidenceSha256 !== null) return invalid;
    const s = d.stages;
    if (!isObj(s) || !exactKeys(s, STAGES_KEYS)) return invalid;
    if (!stageIs(s.speech, rule.speech) || !stageIs(s.word, rule.word) || !captureMatches(s.capture, rule, context.sampleCount)) {
      return invalid;
    }
    const target = context.zh ? ['unsupported', 'unsupported_target'] : ['not_performed', 'not_validated'];
    if (!stageIs(d.targetAssessment, target)) return invalid;
    if (!suggestionsMatch(d.suggestionCodes, d)) return invalid;
    if (d.reason === 'cleanup_unconfirmed') pauseSharedSoundProcessing();
    // Every check above has passed. Guided checks only: attach the typed
    // projection, bound to the fingerprint fixed when Check was chosen.
    const observation = typeof context.fingerprint === 'string' ? guidedObservationOfValidated(d, context.fingerprint) : null;

    if (has(FAILURES, d.reason)) {
      return withObservation(failureView(FAILURES[d.reason], s.capture, d.suggestionCodes, context.word), observation);
    }
    const kind = d.reason === null ? 'matched' : KIND_BY_REASON[d.reason];
    const copy = RESULTS[kind];
    return withObservation({
      title: copy.title(context.word),
      text: copy.text,
      facts: recordingFacts(s.capture),
      next: d.suggestionCodes.map((code) => SUGGESTIONS[code](context.word, false)),
      short: copy.short,
      retry: false,
    }, observation);
  }

  // Free practice views stay exactly as before; only guided views carry this field.
  function withObservation(view, observation) {
    if (observation) view.observation = observation;
    return view;
  }

  function failureView(failure, capture, codes, word) {
    const retry = failure.retry === true;
    let next = [failure.next || (retry ? 'Choose Check again, or keep practicing.' : CAN_STILL)];
    if (codes && codes.length) next = codes.map((code) => SUGGESTIONS[code](word, retry));
    return {
      title: failure.title || 'Could not check this try',
      text: failure.text,
      facts: capture ? recordingFacts(capture) : '',
      next,
      short: 'Not checked',
      retry,
      refresh: failure.refresh === true,
    };
  }

  // Describes the recording only; no thresholds are applied here.
  function recordingFacts(c) {
    if (c.state !== 'observed') return '';
    let level = `average level ${Math.round(-c.rmsDbfs)} dB below maximum`;
    if (c.rms === 0) level = 'no signal';
    else if (c.rmsDbfs <= -120) level = 'average level 120 dB or more below maximum';
    const rails = c.railSamples === 0
      ? 'no samples at the maximum level'
      : `${c.railSamples.toLocaleString('en-US')} ${c.railSamples === 1 ? 'sample' : 'samples'} at the maximum level`;
    return `This try: ${seconds(c.durationMilliseconds / 1000)} · ${level} · ${rails}`;
  }

  // Who is practicing and word check bind every try; changing either clears
  // both tries and fully resets the sound comparison, including its boxes.
  // The controls are locked during a guided session; a change that still
  // arrives ends and clears the whole session, not just its tries.
  function resetForSettings() {
    resetSound(true);
    const ended = endGuidedSession('settings_changed');
    stopVisual();
    const had = ended || app.takes.length > 0 || capturing();
    app.setupGen += 1;
    cancelCapture('');
    clearTakes();
    return had;
  }

  // Both who-is-practicing selects and both opt-in boxes write the same
  // app.practiceContext and app.optIn. Contexts compare structurally. Every
  // change, adult to child and none to adult included, goes through
  // resetForSettings, so the sound comparison is reset in full as well.
  function onPracticeContextChange(event) {
    const select = event && event.target === ui.guidedAge ? ui.guidedAge : ui.age;
    const next = practiceContextOf(select.value);
    if (guidedCanonical(next) === guidedCanonical(app.practiceContext)) return;
    const hadGuided = app.guided !== null;
    const hadSound = app.sound.adult || app.sound.optIn;
    const cleared = resetForSettings();
    app.practiceContext = next;
    if (app.practiceContext === null) app.optIn = false;
    render();
    if (hadGuided) guidedFocusStart();
    const parts = [];
    if (cleared) parts.push(hadGuided ? GUIDED_ENDED_TEXT : CONTEXT_CLEARED_TEXT);
    if (hadSound) parts.push(SOUND_SETTINGS_CLEARED_TEXT);
    if (parts.length) announce(parts.join(' '));
  }

  // Turning word check on never sends anything; each try needs its own Check.
  function onOptInChange(event) {
    const box = event && event.target === ui.guidedOptin ? ui.guidedOptin : ui.procOptin;
    const next = box.checked && practiceContextValid(app.practiceContext) && processingReady();
    const hadGuided = app.guided !== null;
    const hadSound = app.sound.adult || app.sound.optIn;
    const cleared = resetForSettings();
    app.optIn = next;
    render();
    if (hadGuided) guidedFocusStart();
    const state = next ? 'Word check is on. Each try is checked only when you choose Check this try.' : 'Word check is off.';
    const parts = [state];
    if (cleared) parts.push(hadGuided ? GUIDED_ENDED_TEXT : SETTINGS_CLEARED_TEXT);
    if (hadSound) parts.push(SOUND_SETTINGS_CLEARED_TEXT);
    announce(parts.join(' '));
  }

  function onCheckCancel() {
    if (!cancelCheck(STOPPED_TEXT)) return;
    render();
    (ui.fbCheck.hidden ? ui.record : ui.fbCheck).focus();
  }

  function feedbackState() {
    const prompt = selectedPrompt();
    const take = latestTake();
    const result = take ? app.results.get(take.id) : null;
    const check = app.check;
    const g = guidedItem();
    if (g) return guidedFeedbackState(g, prompt, take, result, check);
    if (check.state === 'sending') {
      return { title: 'Checking…', text: 'This usually takes a few seconds and can take up to a minute.' };
    }
    if (capturing()) {
      if (check.state === 'stopped') return { title: 'Check stopped', text: check.text };
      return { title: '', text: 'When you stop, you can listen back and check the new try.' };
    }
    if (result) return Object.assign({ isResult: true }, result);
    if (check.state === 'stopped' && take && check.takeId === take.id) return { title: 'Check stopped', text: check.text };
    const blocker = checkBlocker(prompt);
    if (blocker) return blocker;
    if (!app.optIn) {
      return {
        title: 'Word check is off',
        text: 'Turn it on below to see whether a speech recognition model on this computer recognizes your try as the word. Nothing is sent over the internet.',
      };
    }
    if (!take) return { title: 'Word check is on', text: 'Record a try, then choose Check this try.' };
    return { title: 'Ready to check', text: 'Listen back first if you like, then choose Check this try.' };
  }

  function renderFeedback() {
    const ready = processingReady();
    const sending = app.check.state === 'sending';
    const s = feedbackState();
    ui.fbResult.classList.toggle('is-result', Boolean(s.isResult));
    ui.fbTitle.textContent = s.title || '';
    ui.fbText.textContent = s.text || '';
    ui.fbFacts.textContent = s.facts || '';
    ui.fbNext.replaceChildren(...(s.next || []).map((line) => el('li', { text: line })));

    const take = checkableTake();
    ui.fbCheck.hidden = !take;
    ui.fbCheck.dataset.take = take ? String(take.id) : '';
    ui.fbCheck.textContent = take && app.results.has(take.id) ? 'Check again' : 'Check this try';
    ui.fbCheck.classList.toggle('primary', Boolean(take));
    ui.fbCancel.hidden = !sending;
    ui.fbSetupRetry.hidden = !s.setupRetry;

    const g = guidedItem();
    ui.guidedNext.hidden = !(g && g.round && g.closed && !g.pending);
    ui.guidedNext.textContent = !g || !g.isLast ? 'Next word'
      : g.s.phase === 'first_round' ? 'See first-round summary' : 'See both rounds';
    ui.guidedNext.classList.add('primary');
    ui.guidedSkip.hidden = !(g && g.round && !g.closed);
    ui.guidedRetention.hidden = !g;

    // Settings stay fixed for the whole guided session.
    const locked = app.mode === 'guided' && app.guided !== null;
    ui.fbSettings.hidden = !ready;
    if (locked) ui.fbSettings.open = false;
    // The free choice lives in Say it because it also gates the sound
    // comparison, so it stays usable when word check is unavailable. Guided
    // mode uses its own start-screen select and a fixed session context.
    ui.whoField.hidden = app.mode === 'guided';
    ui.age.value = practiceContextValue(app.practiceContext);
    ui.age.disabled = sending || app.sound.check.state === 'sending' || capturing() || locked;
    ui.procOptin.disabled = !ready || app.practiceContext === null || sending || capturing() || locked;
    ui.procOptin.checked = app.optIn;
    // A locked summary names the session's own fixed context.
    const who = practiceContextLabel(locked ? app.guided.context.practiceContext : app.practiceContext);
    ui.fbSettingsSummary.textContent = locked ? `Word check on · ${who} · fixed for this check`
      : app.optIn ? `Word check on · ${who} · Change` : 'Word check settings';
    ui.procOptinNote.textContent = app.practiceContext === null
      ? CHOOSE_WHO_FREE_TEXT
      : 'Nothing is sent until you choose Check this try for a recording.';
  }

  // ---------- camera mirror ----------

  async function cameraOn() {
    if (app.camera.state !== 'off' || app.cleanupFailed) return;
    if (!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
      app.camera = { state: 'off', stream: null, message: 'This browser cannot use the camera here. Open the page from this computer (localhost) in a current browser.' };
      renderCamera();
      return;
    }
    const gen = ++app.cameraGen;
    app.camera = { state: 'requesting', stream: null, message: '' };
    renderCamera();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      });
    } catch (err) {
      if (gen !== app.cameraGen) return;
      app.camera = { state: 'off', stream: null, message: mediaErrorText(err, 'camera') };
      renderCamera();
      return;
    }
    if (gen !== app.cameraGen) {
      if (!stopStream(stream)) reportCleanupFailure();
      return;
    }
    app.camera.stream = stream;
    for (const track of stream.getVideoTracks()) {
      track.addEventListener('ended', () => {
        if (gen === app.cameraGen) cameraOff('The camera stopped. Turn it on again to keep using the mirror.');
      });
    }
    ui.mirror.srcObject = stream;
    ui.mirror.hidden = false;
    try {
      await ui.mirror.play();
    } catch (_) {
      if (gen !== app.cameraGen) return;
      cameraOff('The camera picture could not be shown. Try again.');
      return;
    }
    if (gen !== app.cameraGen) return;
    app.camera.state = 'on';
    renderCamera();
  }

  function cameraOff(message) {
    stopVisual();
    app.cameraGen += 1;
    const stream = app.camera.stream;
    ui.mirror.pause();
    ui.mirror.srcObject = null;
    ui.mirror.hidden = true;
    app.camera = { state: 'off', stream: null, message: message || '' };
    if (!stopStream(stream)) reportCleanupFailure();
    renderCamera();
  }

  function onCameraToggle() {
    if (app.camera.state === 'off') {
      cameraOn();
      return;
    }
    const wasRequesting = app.camera.state === 'requesting';
    cameraOff(wasRequesting ? 'Cancelled. The camera was not turned on.' : 'Camera is off.');
  }

  function renderCamera() {
    const s = app.camera.state;
    ui.cameraToggle.textContent = { off: 'Turn on camera', requesting: 'Cancel', on: 'Turn off camera' }[s];
    ui.cameraToggle.disabled = s === 'off' && app.cleanupFailed;
    ui.mirrorPlaceholder.hidden = s === 'on';
    ui.mirrorPlaceholder.textContent = s === 'requesting' ? 'Starting camera…' : 'Camera is off';
    let message = app.camera.message;
    if (s === 'requesting') message = 'Waiting for the camera. If the browser asks, choose Allow.';
    else if (s === 'on') message = 'Camera is on. The picture is flipped like a mirror.';
    ui.cameraStatus.textContent = message;
    renderVisual();
  }

  // ---------- optional local visual aid ----------

  function clearOutline() {
    ui.mouthOutline.replaceChildren();
    ui.mouthOutline.hidden = true;
  }

  function renderVisual() {
    const v = app.visual;
    ui.visualOptin.checked = v.enabled;
    ui.visualOptin.disabled = app.camera.state !== 'on' || v.stopping || v.blocked || app.cleanupFailed;
    ui.visualNote.textContent = app.camera.state === 'on'
      ? 'The optional face model runs here in this browser. No camera frames are uploaded.'
      : 'Turn on the camera first. The optional face model runs here in this browser.';
    ui.visualStatus.textContent = v.message;
  }

  async function stopVisual(message = 'Face analysis is off.') {
    const v = app.visual;
    ++v.generation;
    v.enabled = false;
    const runtime = v.runtime;
    v.runtime = null;
    clearOutline();
    v.message = message;
    if (!runtime) { renderVisual(); return; }
    v.stopping = true;
    renderVisual();
    let confirmed = false;
    try {
      const closed = await runtime.stop();
      confirmed = closed.cleanupConfirmed === true;
      ui.visualStatus.dataset.networkBlockedCount = String(closed.networkBlockedCount);
    } catch (_) { /* withheld */ }
    // A later cancellation owns the message; an unconfirmed close always blocks a restart.
    if (!confirmed) {
      v.blocked = true;
      v.message = 'Face analysis is paused because its cleanup could not be confirmed. Reload before using it again.';
    }
    v.stopping = false;
    renderVisual();
  }

  async function startVisual() {
    const v = app.visual;
    if (app.camera.state !== 'on' || v.enabled || v.stopping || v.blocked || app.cleanupFailed) {
      renderVisual(); return;
    }
    const generation = ++v.generation;
    v.enabled = true;
    v.message = 'Starting the local face model…';
    renderVisual();
    const current = () => generation === v.generation && v.enabled && app.camera.state === 'on' && document.visibilityState !== 'hidden';
    try {
      const { LocalVisualRuntime } = await import('/visual-runtime.js');
      if (!current()) return;
      const runtime = new LocalVisualRuntime();
      v.runtime = runtime;
      await runtime.start(ui.mirror, (event) => {
        if (!current()) return;
        clearOutline();
        ui.visualStatus.dataset.networkBlockedCount = String(event.networkBlockedCount);
        const messages = {
          initializing: 'Starting the local face model…',
          ready: 'Looking for one face…',
          tracking: 'Model estimated mouth outline. This is a visual aid only.',
          no_face: 'No face detected. Face the camera so your face is visible.',
          multiple_faces: 'More than one face detected. Show one face to use the outline.',
          unavailable: 'The outline is temporarily unavailable.',
        };
        if (event.status === 'failed' || event.pronunciationFeedbackEligible !== false || event.coordinateSpace !== 'unmirrored_image') {
          stopVisual('The face outline is unavailable. You can keep using the mirror.');
          return;
        }
        v.message = messages[event.status] || 'The outline is unavailable.';
        if (event.status === 'tracking') {
          // The SVG and contained video share pixel dimensions, then mirror together.
          const width = ui.mirror.videoWidth; const height = ui.mirror.videoHeight;
          ui.mouthOutline.setAttribute('viewBox', `0 0 ${width} ${height}`);
          for (const point of event.outline) {
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            for (const key of ['x1', 'x2']) line.setAttribute(key, point[key] * width);
            for (const key of ['y1', 'y2']) line.setAttribute(key, point[key] * height);
            ui.mouthOutline.append(line);
          }
          ui.mouthOutline.hidden = false;
        }
        renderVisual();
      });
      if (!current()) await runtime.stop();
    } catch (_) {
      if (current()) stopVisual('The face outline is unavailable. You can keep using the mirror.');
    }
  }

  // ---------- guided word check ----------

  // The pure section above owns guided metadata. This controller only feeds it
  // events, executes accepted intents through the existing cleanup seams and
  // renders it. The existing capture/check/visual generations stay in force.

  const GUIDED_ENDED_TEXT = 'The guided check ended and its results were cleared.';
  const GUIDED_SETUP_TEXT = 'Word check setup changed on this computer, so the guided check ended and its results were cleared. Start a new guided check to continue.';
  const GUIDED_LIMIT_TEXT = 'This session has reached its recording limit. You can skip the remaining words, see the summary, or end and clear.';
  const GUIDED_CLOSED_TEXT = 'This word is closed for this round. Choose Next word.';
  const GUIDED_ROUND_NEXT = "This is this word's result for this round. You can practice any word after the round.";
  const GUIDED_STOPPED_TEXT = 'No result will be shown. This word is listed as not checked in this round.';
  const GUIDED_ITEM_PHASES = ['first_round', 'recheck', 'practice'];
  const GUIDED_PHASE_NAMES = {
    first_round: 'First round', recheck: 'Recheck', summary: 'First-round summary', practice: 'Practice', comparison: 'Both rounds',
  };
  // Keyed by the pure disposition enum and reason codes; never parsed back out of text.
  const GUIDED_KIND_LABELS = {
    model_matched: 'Recognition matched',
    model_not_matched: 'Recognition did not match',
    recognition_uncertain: 'Word check unsure',
    not_single_supported_word: 'Recognition was not a single supported word',
    speech_not_detected: 'Model did not detect speech',
    recording_issue: 'Recording issue',
    check_unavailable: 'Not checked',
    skipped: 'Skipped',
    not_reached: 'Not reached',
  };
  const GUIDED_ISSUE_LABELS = { silence: 'too quiet to check', clipping: 'samples reached the recording limit', invalid_audio: 'could not be used' };
  const GUIDED_UNAVAILABLE_LABELS = {
    check_cancelled: 'check stopped',
    busy: 'computer busy',
    invalid_response: 'reply could not be verified',
    invalid_request: 'try could not be sent',
    model_unavailable: 'word check unavailable',
    cleanup_unconfirmed: 'word check unavailable',
    source_binding_failed: 'word check unavailable',
  };
  // Rebuild lists only when their content changes, so focus inside them survives.
  const guidedKeys = { roster: '', summary: '', pairs: '' };
  let guidedEndOpener = null;

  // Applies one event. Only an accepted result replaces app.guided, and its
  // clear/reset intents run synchronously before anything else happens.
  function guidedApply(event) {
    if (!app.guided) return null;
    const r = applyGuidedEvent(app.guided, event);
    if (!r.accepted) return r;
    app.guided = r.state;
    if (r.state === null) {
      app.guidedConfirming = false;
      clearGuidedResults();
    }
    for (const action of r.actions) {
      if (action.type === 'clear_media') clearItemMedia();
      else if (action.type === 'require_new_session') app.guidedNotice = GUIDED_SETUP_TEXT;
      // terminate_attempts needs nothing more: clear_media invalidated every
      // capture/check/take callback those attempts owned, and the intent is not kept.
      // start_capture and submit_check are returned to the caller that asked.
    }
    return r;
  }

  // Reset removes result-bearing DOM and its practice-button closures as well as state.
  function clearGuidedResults() {
    for (const list of [ui.guidedRosterList, ui.guidedCounts, ui.guidedRows, ui.guidedPairRows]) list.replaceChildren();
    for (const field of [ui.guidedPhase, ui.guidedSummaryContext, ui.guidedCheckCounts, ui.guidedPairsContext, ui.guidedPairCount]) field.textContent = '';
    guidedKeys.roster = '';
    guidedKeys.summary = '';
    guidedKeys.pairs = '';
    guidedEndOpener = null;
  }

  // The cleanup half of selectPrompt: capture, both tries, playback and face analysis.
  function clearItemMedia() {
    resetSound(true);
    stopVisual();
    stopExample();
    cancelCapture('');
    clearTakes();
    app.rec = { state: 'idle', message: '', elapsed: 0, level: 0 };
  }

  // end | settings_changed | hidden | pagehide | free_practice. Clears every
  // piece of session metadata, both tries and their URLs. Repeats are inert.
  function endGuidedSession(type) {
    if (!app.guided) return false;
    const r = guidedApply({ type });
    if (!r || !r.accepted) return false;
    app.guidedNotice = GUIDED_ENDED_TEXT;
    return true;
  }

  function refreshGuidedContext() {
    if (!app.guided) return;
    const r = guidedApply({
      type: 'context_refresh', catalog: app.prompts, declaration: app.declaration,
      practiceContext: app.practiceContext, setupGeneration: app.setupGen, optIn: app.optIn,
    });
    if (!r || !r.accepted || r.state !== null) return;
    render();
    guidedFocusStart();
    announce(GUIDED_SETUP_TEXT);
  }

  function guidedViewWithoutMirror() {
    return app.mode === 'guided' && !(app.guided && GUIDED_ITEM_PHASES.includes(app.guided.phase));
  }

  function enforceGuidedCamera() {
    if (!guidedViewWithoutMirror() || app.camera.state === 'off') return false;
    cameraOff('');
    return true;
  }

  // Facts about the current guided word, or null outside a round or practice.
  function guidedItem() {
    const s = app.mode === 'guided' ? app.guided : null;
    if (!s || !s.currentItemId || !GUIDED_ITEM_PHASES.includes(s.phase)) return null;
    const round = s.phase === 'first_round' ? s.first : s.phase === 'recheck' ? s.recheck : null;
    const id = s.currentItemId;
    const closed = round !== null && round.dispositionsByItemId[id].kind !== 'not_reached';
    const pending = app.check.state === 'sending' || s.attempts.some((a) => a.itemId === id && a.submitted && a.terminalCode === null);
    const capReached = s.attempts.length >= GUIDED_ATTEMPT_LIMIT;
    const index = round ? round.plannedItemIds.indexOf(id) : s.context.roster.findIndex((r) => r.itemId === id);
    return {
      s, round, index, closed, pending, capReached,
      isLast: round !== null && index === round.plannedItemIds.length - 1,
      recordAllowed: !closed && !pending && !capReached,
    };
  }

  function guidedWord(s, itemId) {
    const row = s.context.roster.find((r) => r.itemId === itemId);
    return row ? row.word : '';
  }

  function guidedRowLabel(d) {
    const base = GUIDED_KIND_LABELS[d.kind] || 'Not checked';
    if (d.kind === 'recording_issue' && typeof d.reason === 'string' && has(GUIDED_ISSUE_LABELS, d.reason)) {
      return `${base}: ${GUIDED_ISSUE_LABELS[d.reason]}`;
    }
    if (d.kind === 'check_unavailable' && d.reason !== 'check_pending') {
      const why = typeof d.reason === 'string' && has(GUIDED_UNAVAILABLE_LABELS, d.reason) ? GUIDED_UNAVAILABLE_LABELS[d.reason] : 'check did not finish';
      return `${base}: ${why}`;
    }
    return base;
  }

  // Settles a finished guided check exactly once and returns the view to show,
  // or null when the check no longer owns its attempt.
  function settleGuidedCheck(owner, view, word) {
    if (!guidedOwns(app.guided, owner)) return null;
    let r = null;
    if (view.observation) r = guidedApply({ type: 'observation', owner, observation: view.observation });
    let shown = view;
    if (!r || !r.accepted) {
      const code = view.observation ? 'invalid_response' : (view.localCode || 'check_failed');
      r = guidedApply({ type: 'attempt_terminal', owner, code });
      if (!r || !r.accepted) return null;
      if (view.observation) shown = failureView(OUTCOME.invalid, null, null, word);
    }
    // Copy only display fields; nothing from the reply enters guided state here.
    const next = owner.roundId !== null ? [GUIDED_ROUND_NEXT]
      : shown.retry ? ['Record a fresh try to check again.'] : shown.next;
    return {
      title: shown.title, text: shown.text, facts: shown.facts, next, short: shown.short,
      retry: false, refresh: shown.refresh === true,
    };
  }

  function guidedFeedbackState(g, prompt, take, result, check) {
    const inRound = g.round !== null;
    if (check.state === 'sending') {
      return {
        title: 'Checking…',
        text: `This usually takes a few seconds and can take up to a minute.${inRound ? ' If you stop waiting, this word is listed as not checked in this round.' : ''}`,
      };
    }
    const stoppedText = inRound ? GUIDED_STOPPED_TEXT : check.text;
    if (capturing()) {
      if (check.state === 'stopped') return { title: 'Check stopped', text: stoppedText };
      return { title: '', text: 'When you stop, you can listen back and check the new try.' };
    }
    if (result) return Object.assign({ isResult: true }, result);
    if (check.state === 'stopped' && take && check.takeId === take.id) return { title: 'Check stopped', text: stoppedText };
    if (g.closed) return { title: 'Closed for this round', text: GUIDED_CLOSED_TEXT };
    const blocker = checkBlocker(prompt);
    if (blocker) return blocker;
    if (!take) {
      return inRound
        ? { title: 'Record, then check', text: `Record ${quote(prompt.word)}, listen back if you like, then choose Check this try. Or skip this word.` }
        : { title: 'Practice', text: 'Record a try, then choose Check this try. Each try can be checked once.' };
    }
    if (!checkableTake()) return { title: '', text: 'Each try can be checked once. Record a fresh try to check again.' };
    return inRound
      ? { title: 'Ready to check', text: "The first Check is this word's result for this round." }
      : { title: 'Ready to check', text: 'Listen back first if you like, then choose Check this try.' };
  }

  function guidedStartBlocker() {
    if (app.cleanupFailed) return 'Reload the page before recording again.';
    if (app.catalogState === 'loading' || app.declarationState === 'loading') return 'Checking whether word check is available…';
    const blocker = checkBlocker(null);
    if (blocker && (blocker.title || blocker.text)) return `${blocker.title || 'Word check is not available'}. Practice freely still works.`;
    if (!practiceContextValid(app.practiceContext)) return CHOOSE_WHO_TEXT;
    if (!app.optIn) return 'Turn on Check my tries on this computer.';
    if (!captureSupported()) return 'This browser cannot record here. Open the page from this computer (localhost) in a current browser.';
    if (app.catalogState !== 'ready' || !guidedRoster(app.prompts)) return 'Guided word check is not available right now. Practice freely still works.';
    return '';
  }

  function guidedFocusStart() {
    if (ui.guidedStart.hidden) return;
    const active = document.activeElement;
    if (!active || active === document.body || active.closest('[hidden]')) ui.guidedStartHeading.focus();
  }

  // ----- actions -----

  function onModeGuided() {
    if (app.mode === 'guided') return;
    const had = app.takes.length > 0 || capturing();
    const cameraWasOn = app.camera.state !== 'off';
    clearItemMedia();
    app.mode = 'guided';
    app.guidedNotice = '';
    app.guidedConfirming = false;
    renderPractice();
    render();
    ui.guidedStartHeading.focus();
    const message = `${had ? 'Your tries were cleared.' : ''}${cameraWasOn ? ' Camera turned off.' : ''}`.trim();
    if (message) announce(message);
  }

  function onModeFree() {
    if (app.mode === 'free') return;
    endGuidedSession('free_practice');
    clearItemMedia();
    cameraOff('');
    app.mode = 'free';
    app.guidedNotice = '';
    app.guidedConfirming = false;
    ui.fbSettings.open = true;
    renderPractice();
    render();
    ui.practice.focus();
  }

  // Selecting a mode or starting never touches the microphone, camera or network.
  function onGuidedBegin() {
    if (app.mode !== 'guided' || app.guided || guidedStartBlocker() || capturing() || app.check.state === 'sending') {
      render();
      return;
    }
    const state = makeGuidedSession(app.prompts, app.declaration, app.practiceContext, {
      id: uuid(), generation: ++app.guidedGen, setupGeneration: app.setupGen, optIn: app.optIn,
    });
    if (!state) {
      render();
      return;
    }
    clearItemMedia();
    app.guided = state;
    app.guidedNotice = '';
    app.guidedConfirming = false;
    renderPractice();
    render();
    // Deliberately not Record, so a held key cannot start the microphone.
    ui.practice.focus();
    announce(`First round. Word 1 of ${state.first.plannedItemIds.length}: ${guidedWord(state, state.currentItemId)}.`);
  }

  function guidedNavigate(event) {
    const hadTakes = app.takes.length > 0 || capturing();
    const r = guidedApply(event);
    if (!r || !r.accepted) {
      render();
      return null;
    }
    app.guidedConfirming = false;
    const cameraStopped = enforceGuidedCamera();
    renderPractice();
    render();
    return { extra: `${hadTakes ? ' Recordings from the last word were cleared.' : ''}${cameraStopped ? ' Camera turned off.' : ''}` };
  }

  function guidedArrived(nav, lead = '') {
    const s = app.guided;
    if (s.phase === 'summary' || s.phase === 'comparison') {
      (s.phase === 'summary' ? ui.guidedSummaryHeading : ui.guidedPairsHeading).focus();
      const message = `${lead}${nav.extra}`.trim();
      if (message) announce(message);
      return;
    }
    ui.practice.focus();
    const word = guidedWord(s, s.currentItemId);
    if (s.phase === 'practice') {
      announce(`${lead}Practicing ${word}. Tries here don't change the round results.${nav.extra}`);
      return;
    }
    const g = guidedItem();
    const opening = g.index === 0 ? `${GUIDED_PHASE_NAMES[s.phase]}. ` : '';
    announce(`${lead}${opening}Word ${g.index + 1} of ${g.round.plannedItemIds.length}: ${word}.${nav.extra}`);
  }

  function onGuidedNext() {
    const nav = guidedNavigate({ type: 'next' });
    if (nav) guidedArrived(nav);
  }

  function onGuidedSkip() {
    const s = app.guided;
    const word = s ? guidedWord(s, s.currentItemId) : '';
    const nav = guidedNavigate({ type: 'skip' });
    if (nav) guidedArrived(nav, `Skipped ${word}. `);
  }

  // Any pending check is cancelled through the normal clear path.
  function onGuidedFinish() {
    const nav = guidedNavigate({ type: 'finish_round' });
    if (nav) guidedArrived(nav);
  }

  function onGuidedPractice(itemId, fromRoster = false) {
    const s = app.guided;
    if (!s || (s.phase === 'practice' && s.currentItemId === itemId)) return;
    const nav = guidedNavigate({ type: 'practice_word', itemId });
    if (!nav) return;
    if (fromRoster && !narrowScreen()) {
      const button = Array.from(ui.guidedRosterList.querySelectorAll('button.word-row')).find((b) => b.dataset.item === itemId);
      if (button) {
        button.focus();
        announce(`Practicing ${guidedWord(app.guided, itemId)}.${nav.extra}`);
        return;
      }
    }
    guidedArrived(nav);
  }

  function onGuidedBack() {
    const itemId = app.guided ? app.guided.currentItemId : null;
    const nav = guidedNavigate({ type: 'return_summary' });
    if (!nav) return;
    const button = Array.from(ui.guidedRows.querySelectorAll('button.g-practice')).find((b) => b.dataset.item === itemId);
    if (button && !ui.guidedSummary.hidden) button.focus();
    else (app.guided.phase === 'summary' ? ui.guidedSummaryHeading : ui.guidedPairsHeading).focus();
    if (nav.extra) announce(nav.extra.trim());
  }

  // Exactly one full fresh round of all 13 words; no subset recheck exists.
  function onGuidedRecheck() {
    const nav = guidedNavigate({ type: 'start_recheck' });
    if (nav) guidedArrived(nav);
  }

  function onGuidedEndOpen(event) {
    if (!app.guided) return;
    guidedEndOpener = event.currentTarget;
    app.guidedConfirming = true;
    render();
    ui.guidedEndNo.focus();
  }

  function onGuidedEndKeep() {
    if (!app.guidedConfirming) return;
    app.guidedConfirming = false;
    render();
    const opener = guidedEndOpener && !guidedEndOpener.closest('[hidden]') ? guidedEndOpener : ui.guidedEnd;
    guidedEndOpener = null;
    opener.focus();
  }

  function onGuidedEndYes() {
    const cameraWasOn = app.camera.state !== 'off';
    if (!endGuidedSession('end')) return;
    guidedEndOpener = null;
    render();
    ui.guidedStartHeading.focus();
    announce(`${GUIDED_ENDED_TEXT}${cameraWasOn ? ' Camera turned off.' : ''}`);
  }

  // ----- rendering -----

  // A listening focus from the canonical word, never a judgment of a try.
  function brPractice() {
    if (app.mode !== 'free' || app.guided !== null) return null;
    const prompt = selectedPrompt();
    const canonical = GUIDED_CANONICAL_CATALOG.find((p) => p.id === 'r-middle-bread');
    if (!prompt || prompt.id !== canonical.id ||
        canonicalJson(prompt.processingPrompt) !== canonicalJson(canonical.processingPrompt) ||
        !exampleSource) return null;
    const take = latestTake();
    const current = take && take.promptId === prompt.id && take.setupGen === app.setupGen &&
      !take.guidedOwner ? take : null;
    return { prompt, take: current };
  }

  function renderBrPractice() {
    const practice = brPractice();
    const take = practice && practice.take;
    ui.brCue.hidden = !practice;
    ui.brCue.textContent = practice
      ? 'For bread, play the example and listen for b, then r, at the start of the whole word. Say bread once, then play your try back.'
      : '';
    ui.brActions.hidden = !take || capturing();
    ui.brTake.dataset.take = take ? String(take.id) : '';
    ui.brTake.textContent = take && playback.takeId === take.id ? 'Stop this try' : 'Play this try';
    ui.brTake.disabled = !take || capturing();
    ui.brRecord.disabled = !take || capturing() || ui.record.disabled;
  }

  function onBrExample() {
    if (!brPractice() || capturing()) return;
    toggleExample();
  }

  function onBrTake() {
    const practice = brPractice();
    const id = Number(ui.brTake.dataset.take);
    if (!practice || !practice.take || practice.take.id !== id || capturing()) return;
    toggleTake(id);
  }

  function onBrRecord() {
    const practice = brPractice();
    if (!practice || !practice.take || capturing() || ui.record.disabled) return;
    onRecordClick();
    // This named region stays visible through startup, failure and Stop.
    // Focus must not follow Cancel, which disappears after permission resolves.
    ui.recordPanel.focus();
  }

  function renderGuided() {
    const guided = app.mode === 'guided';
    const s = guided ? app.guided : null;
    const phase = !guided ? 'free' : s ? s.phase : 'start';
    const inItem = GUIDED_ITEM_PHASES.includes(phase);
    ui.modeBar.hidden = !(phase === 'free' || phase === 'start');
    ui.modeFree.setAttribute('aria-pressed', String(!guided));
    ui.modeGuided.setAttribute('aria-pressed', String(guided));
    ui.guidedBar.hidden = !s;
    ui.guidedPhase.textContent = s ? GUIDED_PHASE_NAMES[phase] : '';
    ui.guidedBack.hidden = phase !== 'practice';
    const confirming = Boolean(s) && app.guidedConfirming;
    ui.guidedEnd.setAttribute('aria-expanded', String(confirming));
    ui.guidedEndConfirm.hidden = !confirming;
    ui.guidedStart.hidden = phase !== 'start';
    ui.practice.hidden = !(phase === 'free' || inItem);
    ui.guidedSummary.hidden = phase !== 'summary';
    ui.guidedPairs.hidden = phase !== 'comparison';
    ui.words.hidden = phase !== 'free';
    ui.guidedRoster.hidden = !inItem;
    const layout = ui.practice.closest('.layout');
    if (layout) layout.classList.toggle('is-full', ['start', 'summary', 'comparison'].includes(phase));
    for (const link of ui.practice.querySelectorAll('.change-word')) link.hidden = guided;

    if (phase === 'start') renderGuidedStart();
    if (inItem) renderGuidedRoster(s);
    else guidedKeys.roster = '';
    if (phase === 'summary') renderGuidedSummary(s);
    else guidedKeys.summary = '';
    if (phase === 'comparison') renderGuidedPairs(s);
    else guidedKeys.pairs = '';
  }

  function renderGuidedStart() {
    const ready = processingReady();
    const busy = capturing() || app.check.state === 'sending';
    ui.guidedStartNotice.hidden = !app.guidedNotice;
    ui.guidedStartNotice.textContent = app.guidedNotice;
    ui.guidedAge.value = practiceContextValue(app.practiceContext);
    ui.guidedAge.disabled = !ready || busy;
    ui.guidedOptin.checked = app.optIn;
    ui.guidedOptin.disabled = !ready || app.practiceContext === null || busy;
    ui.guidedOptinNote.textContent = app.practiceContext === null
      ? CHOOSE_WHO_TEXT
      : 'Nothing is sent until you choose Check this try for a recording.';
    const blocker = guidedStartBlocker();
    ui.guidedBegin.disabled = Boolean(blocker) || busy;
    ui.guidedStartStatus.textContent = blocker;
  }

  // Rounds: read-only status, never a result. Practice: manual word buttons.
  function renderGuidedRoster(s) {
    const round = s.phase === 'first_round' ? s.first : s.phase === 'recheck' ? s.recheck : null;
    ui.guidedFinish.hidden = !round;
    ui.guidedFinishNote.hidden = !round;
    const kinds = round ? round.plannedItemIds.map((id) => round.dispositionsByItemId[id].kind).join(',') : '';
    const key = [s.id, s.phase, s.currentItemId, kinds].join('|');
    if (key === guidedKeys.roster) return;
    guidedKeys.roster = key;
    ui.guidedRosterList.replaceChildren(...s.context.roster.map((r) => {
      const current = r.itemId === s.currentItemId;
      if (!round) {
        return el('li', null, el('button', {
          type: 'button',
          class: 'word-row',
          'data-item': r.itemId,
          'aria-current': current ? 'true' : null,
          onclick: () => onGuidedPractice(r.itemId, true),
        }, el('span', { text: r.word })));
      }
      const d = round.dispositionsByItemId[r.itemId];
      const status = current ? 'Current' : d.kind === 'skipped' ? 'Skipped' : d.kind === 'not_reached' ? 'Not yet' : 'Finished';
      return el('li', { 'aria-current': current ? 'step' : null },
        el('span', { text: r.word }), ' ', el('span', { class: 'word-row-pos', text: status }));
    }));
  }

  function guidedCountFacts(sum) {
    // Only non-zero categories, in the pure enum order; they add up to 13.
    const facts = Object.keys(sum.counts).filter((k) => sum.counts[k] > 0)
      .flatMap((k) => fact(GUIDED_KIND_LABELS[k] || k, String(sum.counts[k])));
    return [...facts, ...fact('Planned words', String(sum.planned))];
  }

  function renderGuidedSummary(s) {
    const key = `${s.id}|${s.attempts.length}`;
    if (key === guidedKeys.summary) return;
    guidedKeys.summary = key;
    const sum = summarizeRound(s.first, s.attempts);
    const practiceTries = s.attempts.filter((a) => a.purpose === 'practice').length;
    ui.guidedSummaryHeading.textContent = 'First round';
    ui.guidedSummaryContext.textContent = `${practiceContextLabel(s.context.practiceContext)} · ${sum.planned} words${s.first.finishedEarly ? ` · round finished early; ${sum.counts.not_reached} not reached` : ''}`;
    ui.guidedCounts.replaceChildren(...guidedCountFacts(sum));
    // Recordings, explicit Checks, actual POSTs, verified replies and whole-word results stay distinct.
    ui.guidedCheckCounts.textContent = `Recordings started: ${sum.recordingAttempts}. Checks chosen: ${sum.submittedChecks}. `
      + `Checks sent: ${sum.httpPosts}. Verified replies: ${sum.verifiedResponses}. `
      + `Words with a whole-word recognition result: ${sum.lexicalObservations} of ${sum.planned}.`
      + (practiceTries ? ` Practice recordings: ${practiceTries}; they are not part of these rows.` : '');
    ui.guidedRows.replaceChildren(...sum.rows.map((row, i) => {
      const word = guidedWord(s, row.itemId);
      return el('li', { class: 'g-row' },
        el('span', { class: 'g-num', text: String(i + 1) }),
        el('span', { class: 'g-word', text: word }),
        el('span', { class: 'g-obs', text: guidedRowLabel(row) }),
        el('button', {
          type: 'button',
          class: 'button g-practice',
          'data-item': row.itemId,
          'aria-label': `Practice ${word}`,
          onclick: () => onGuidedPractice(row.itemId),
        }, 'Practice'));
    }));
    ui.guidedRecheck.disabled = s.recheck !== null;
  }

  function renderGuidedPairs(s) {
    const key = `${s.id}|${s.attempts.length}`;
    if (key === guidedKeys.pairs) return;
    guidedKeys.pairs = key;
    const cmp = compareRounds(s.first, s.recheck, s.attempts);
    if (!cmp) {
      ui.guidedPairsContext.textContent = 'These rounds cannot be shown side by side.';
      ui.guidedPairCount.textContent = '';
      ui.guidedPairRows.replaceChildren();
      return;
    }
    // Both rounds share one session context, so one fixed label covers both.
    ui.guidedPairsContext.textContent = `${practiceContextLabel(s.context.practiceContext)} in both rounds · same ${cmp.plannedPairs} words and the same word check setup.`;
    ui.guidedPairCount.textContent = `Words with a whole-word recognition result in both rounds: ${cmp.pairsWithTwoLexicalObservations} of ${cmp.plannedPairs}. `
      + 'Each submitted recheck used a new recording attempt. Identical audio is marked below; skipped or unreached words have no comparison. These results do not establish progress or consistency.';
    ui.guidedPairRows.replaceChildren(...cmp.rows.map((row, i) => {
      const details = [];
      if (row.comparison === 'no_comparison') details.push('No comparison.');
      if (row.sameAudioBytes) details.push('The recheck recording had exactly the same audio bytes as the first round, so the two are not separate evidence.');
      return el('li', { class: 'g-row g-pair' },
        el('span', { class: 'g-num', text: String(i + 1) }),
        el('span', { class: 'g-word', text: guidedWord(s, row.itemId) }),
        el('dl', { class: 'g-pair-facts' },
          ...fact('First round', guidedRowLabel(row.first)),
          ...fact('Recheck', guidedRowLabel(row.recheck))),
        details.length ? el('p', { class: 'g-detail', text: details.join(' ') }) : null);
    }));
  }

  // ---------- leaving the page ----------

  // Hidden or closing: stop every sensor, clear both tries and stop waiting
  // for a check. The server may still finish an attempt it has.
  function pauseForBackground(reason = 'hidden') {
    resetSound(true);
    // A guided session never resumes after the page was hidden or closed.
    const ended = endGuidedSession(reason);
    const active = ended || app.capture || app.takes.length || app.camera.state !== 'off' || app.check.state === 'sending';
    stopVisual();
    stopExample();
    cancelCapture('');
    clearTakes();
    if (app.camera.state !== 'off') cameraOff('');
    if (active) app.rec = { state: 'idle', message: PAUSED_TEXT, elapsed: 0, level: 0 };
    render();
  }

  function onPageHide() {
    pauseForBackground('pagehide');
    app.session = newSession();
    renderSession();
  }

  // ---------- rendering ----------

  function renderRecorder() {
    const s = app.rec.state;
    ui.record.textContent = {
      idle: latestTake() ? 'Record again' : 'Record',
      requesting: 'Starting…',
      recording: 'Stop',
      finishing: 'Finishing…',
    }[s];
    // Guided: no Record while a check is sending, after the round word closed,
    // or once the session's attempt bound is reached.
    const g = guidedItem();
    const guidedBlocked = Boolean(g) && s === 'idle' && !g.recordAllowed;
    ui.record.disabled = !selectedPrompt() || app.cleanupFailed || s === 'requesting' || s === 'finishing' || guidedBlocked;
    // One dark button at a time: Check when it is offered, nothing while
    // waiting for a check, otherwise Record.
    ui.record.classList.toggle('primary', s === 'recording' || (!checkableTake() && app.check.state !== 'sending' && !guidedBlocked));
    ui.recordCancel.hidden = s !== 'requesting';
    ui.recordPanel.classList.toggle('is-recording', s === 'recording');
    let message = app.rec.message;
    if (s === 'requesting') message = 'Waiting for the microphone. If the browser asks, choose Allow.';
    else if (s === 'recording') message = 'Recording. Say the word, then tap Stop.';
    else if (s === 'finishing') message = 'Finishing the recording…';
    else if (g && g.closed && !g.pending) message = GUIDED_CLOSED_TEXT;
    else if (g && g.capReached) message = GUIDED_LIMIT_TEXT;
    ui.recordStatus.textContent = message;
  }

  function renderMeters() {
    const take = latestTake();
    const elapsed = app.rec.state === 'idle' && take ? take.sampleCount / TARGET_RATE : app.rec.elapsed;
    ui.timeFill.style.transform = `scaleX(${Math.min(1, elapsed / MAX_SECONDS)})`;
    ui.timeText.textContent = `${seconds(elapsed)} of ${MAX_SECONDS} s`;
    const level = app.rec.state === 'recording' ? Math.sqrt(app.rec.level) : 0;
    ui.levelFill.style.transform = `scaleX(${level})`;
  }

  function shortResult(take) {
    if (app.check.state === 'sending' && app.check.takeId === take.id) return 'Checking…';
    const view = app.results.get(take.id);
    return view ? view.short : 'Not checked';
  }

  function renderTryRow(row, take, label) {
    row.item.hidden = !take;
    if (!take) {
      row.play.dataset.take = '';
      return;
    }
    const playing = playback.takeId === take.id;
    row.label.textContent = label;
    row.length.textContent = seconds(take.sampleCount / TARGET_RATE);
    row.result.textContent = shortResult(take);
    row.play.dataset.take = String(take.id);
    row.play.textContent = playing ? 'Stop' : 'Play';
    row.play.setAttribute('aria-label', `${playing ? 'Stop' : 'Play'} ${label.toLowerCase()}`);
    row.play.disabled = capturing();
  }

  function renderCompare() {
    const takes = app.takes;
    ui.compare.hidden = takes.length === 0;
    renderBrPractice();
    if (!takes.length) return;
    const latest = latestTake();
    const earlier = takes.length > 1 ? takes[0] : null;
    renderTryRow(ui.rows[0], earlier, 'Earlier try');
    renderTryRow(ui.rows[1], latest, earlier ? 'Latest try' : 'Your try');
    const p = selectedPrompt();
    const pos = p ? positionOf(p.id) : '';
    ui.compareHint.textContent = earlier
      ? `Play each try, then the example${pos ? `, and listen for the ${pos} sound` : ''}.`
      : 'Record another try to compare the two.';
    ui.compareNote.hidden = !earlier;
    ui.takesClear.textContent = earlier ? 'Clear tries' : 'Clear try';
    ui.takesClear.disabled = capturing();
  }

  function renderSession() {
    const { recordings } = app.session;
    const words = app.session.words.size;
    ui.sessionNote.hidden = recordings === 0 || app.mode === 'guided';
    ui.sessionCount.textContent = `This session: ${recordings} ${recordings === 1 ? 'recording' : 'recordings'} of ${words} ${words === 1 ? 'word' : 'words'}.`;
  }

  function renderCleanup() {
    ui.cleanupNotice.hidden = !app.cleanupFailed;
  }

  function render() {
    // No hidden <video> keeps the camera running on a guided view without a mirror.
    enforceGuidedCamera();
    renderGuided();
    renderRecorder();
    renderMeters();
    renderFeedback();
    renderCompare();
    renderExample();
    renderCamera();
    renderSession();
    renderCleanup();
    renderSound();
    renderBrPractice();
  }

  const SOUND_FIXED_SOURCES = {"workerSourceSha256":"e392c577e289dcb944551bc95c2ea1ad05a39d420f18b5a6eb3a08d668e7ba04","workerReceiptSha256":"0c1762b9b6cab1499cb541663601bd261e03afba33e2e3453a6af35aebc50ca3","runtimePinsSha256":"908e50025533f9fa85bf1a4d3e89d30a9caa2b9f4883788b4188fedd5cb5751e","contrastSpecSha256":"3f49f4bee3664e42663af5b44bce86bab61d3593f63a72875973500b71849844","modelFileSha256":"3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120","vocabularyFileSha256":"d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0","promptSha256":"7910f87e3a252ae0b3a41dfa45649a122c461b7b1ca7fda67f6c309ab4c56383","resourcePolicySha256":"844dce27ead916bc51cf4909d70a33bec9e473ef174805d371196352f32085e4"};
  const SOUND_CONTRAST = {"contrastId":"bread-r-w-v1","contrastSpecSha256":"3f49f4bee3664e42663af5b44bce86bab61d3593f63a72875973500b71849844","checkpointId":"onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX","checkpointRevision":"c69750f5043e5e1f8a71ab95dd3b98338c280c92","configFileSha256":"428b7781d080ad9463dca0e17e5066073cb691bfc14a178a85e76ac79c1f4a0f","ctcSourceSha256":"afaad92d487f2880e211c60232c5c9b94c9e05c40ce5c44d06a058159fab011b","manifestSourceSha256":"1e07477079fa4425dacfbe271ba6c7ede472bf099d5f6914b8e4cc535053e148","modelFileSha256":"3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120","posteriorSourceSha256":"0c4672fb8d132437b3d120812a5785cd2a2858d365cbec016523c0b5f3a57087","preprocessorFileSha256":"a2254a5b58f72cd4de3632f8eee64f3f098b7c1402128d2f419e7d00ae13e335","runtime":"@huggingface/transformers@4.2.0","upstreamRevision":"ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4","vocabularyFileSha256":"d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0","phoneIndex":1,"promptId":"r-middle-bread","promptSha256":"7910f87e3a252ae0b3a41dfa45649a122c461b7b1ca7fda67f6c309ab4c56383","targetPhone":"R","wordIndex":0};
  // Closed development sound boundary, separate from word feedback and guided observations.
  const SOUND_KIND = 'engineering_sound_observation';
  const SOUND_PURPOSE = 'adult-development-preview';
  const SOUND_CLAIMS = ['calibrationValidated','pronunciationCorrectnessAssessed','diagnosisProvided','childAccuracyEstablished','learnerFeedbackEligible','clinicalUseEligible','productionUseEligible'];
  const SOUND_SOURCE_KEYS = ['featureSourceSha256','workerSourceSha256','workerReceiptSha256','runtimePinsSha256','contrastSpecSha256','modelFileSha256','vocabularyFileSha256','promptSha256','resourcePolicySha256'];
  const SOUND_OWNER_KEYS = ['sessionId','generation','roundId','roundKind','itemId','takeId','captureId','contextSha256'];
  const SOUND_INCONCLUSIVE = ['insufficient_frames','zero_candidate_mass','candidate_tie','uncovered_mass_dominates','greedy_tie','decoded_context_outside_candidates','decoded_path_disagreement'];
  const SOUND_UNAVAILABLE = ['busy','cancelled','timeout','cleanup_unconfirmed','source_binding_failed','stale_ownership','worker_unavailable','invalid_evidence','capture_already_checked','attempt_already_checked','attempt_limit','context_limit','processing_unavailable','binding_mismatch','invalid_frames','frame_limit','numerical_mass_invalid'];
  const SOUND_POLICY = {id:'adult-development-sound-preview-v1',purpose:SOUND_PURPOSE,promptId:'r-middle-bread',practiceMode:'free',minimumSamples:2400,maximumSamples:64000,maximumClaims:128,maximumContexts:8,encoderInput:'bytes-only',projection:'uncalibrated-model-preference-no-numeric-diagnostics',claimLimits:Object.fromEntries(SOUND_CLAIMS.map(k=>[k,false]))};
  const soundUuid = v => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(v);
  function soundFalseClaims(v) { return isObj(v) && exactKeys(v,SOUND_CLAIMS) && SOUND_CLAIMS.every(k=>v[k]===false); }
  function soundWordBinding(d) {
    return d && {pins:d.pins,feedbackSourceSha256:d.feedbackSourceSha256,wrapperSourceSha256:d.wrapperSourceSha256,feedbackPolicySha256:d.feedbackPolicySha256,contentSha256:d.contentSha256};
  }
  function soundSource(v,wordDeclaration) {
    if (!isObj(v) || !exactKeys(v,['sources','wordBinding']) || !isObj(v.sources) || !exactKeys(v.sources,SOUND_SOURCE_KEYS) || !SOUND_SOURCE_KEYS.every(k=>isHex(v.sources[k]))) return false;
    if (!isObj(v.wordBinding) || !exactKeys(v.wordBinding,['pins','feedbackSourceSha256','wrapperSourceSha256','feedbackPolicySha256','contentSha256']) || !isObj(v.wordBinding.pins) || !exactKeys(v.wordBinding.pins,PIN_KEYS) || !PIN_KEYS.every(k=>isHex(v.wordBinding.pins[k]))) return false;
    if (!['feedbackSourceSha256','wrapperSourceSha256','feedbackPolicySha256','contentSha256'].every(k=>isHex(v.wordBinding[k]))) return false;
    if (!Object.entries(SOUND_FIXED_SOURCES).every(([k,value])=>v.sources[k]===value)) return false;
    return !wordDeclaration || canonicalJson(v.wordBinding)===canonicalJson(soundWordBinding(wordDeclaration));
  }
  function normalizeSoundDeclaration(d,wordDeclaration) {
    try {
      if (!isObj(d) || !exactKeys(d,['schemaVersion','kind','purpose','serverNonce','csrfToken','binding','policy','processingAvailable','claimLimits']) || d.schemaVersion!==1 || d.kind!==SOUND_KIND || d.purpose!==SOUND_PURPOSE || !soundUuid(d.serverNonce) || !isHex(d.csrfToken) || typeof d.processingAvailable!=='boolean' || !soundFalseClaims(d.claimLimits)) return null;
      if (!soundSource(d.binding,wordDeclaration) || canonicalJson(d.policy)!==canonicalJson(SOUND_POLICY)) return null;
      return JSON.parse(canonicalJson(d));
    } catch (_) { return null; }
  }
  function soundOwner(v) {
    return isObj(v) && exactKeys(v,SOUND_OWNER_KEYS) && ['sessionId','roundId','takeId','captureId'].every(k=>typeof v[k]==='string' && /^[A-Za-z0-9_-]{1,64}$/.test(v[k])) && Number.isInteger(v.generation) && v.generation>=1 && v.generation<=2147483647 && v.roundKind==='probe' && v.itemId==='r-middle-bread' && isHex(v.contextSha256);
  }
  function soundExpected(v) {
    return isObj(v) && exactKeys(v,['attemptId','requestSha256','workerRequestSha256','ownership','audio','source']) && soundUuid(v.attemptId) && isHex(v.requestSha256) && isHex(v.workerRequestSha256) && soundOwner(v.ownership) && isObj(v.audio) && exactKeys(v.audio,['sha256','bytes','sampleCount','sampleRateHertz']) && isHex(v.audio.sha256) && Number.isInteger(v.audio.sampleCount) && v.audio.sampleCount>=2400 && v.audio.sampleCount<=64000 && v.audio.bytes===44+v.audio.sampleCount*2 && v.audio.sampleRateHertz===16000 && soundSource(v.source);
  }
  function interpretSound(d,expected) {
    try {
      if (!soundExpected(expected) || !isObj(d) || !exactKeys(d,['schemaVersion','kind','purpose','status','reason','modelPreference','binding','claimLimits']) || d.schemaVersion!==1 || d.kind!==SOUND_KIND || d.purpose!==SOUND_PURPOSE || !soundFalseClaims(d.claimLimits) || canonicalJson(d.binding)!==canonicalJson(expected)) return null;
      if (d.status==='observed_model_preference') {
        if (d.reason!=='model_preferred_candidate' || !['r_path','w_path','other_path'].includes(d.modelPreference)) return null;
      } else if (d.status==='inconclusive') {
        if (!SOUND_INCONCLUSIVE.includes(d.reason) || d.modelPreference!==null) return null;
      } else if (d.status==='unavailable') {
        if (!SOUND_UNAVAILABLE.includes(d.reason) || d.modelPreference!==null) return null;
      } else if (d.status==='unsupported') {
        if (d.reason!=='unsupported_prompt' || d.modelPreference!==null) return null;
      } else return null;
      return Object.freeze({status:d.status,reason:d.reason,modelPreference:d.modelPreference});
    } catch (_) { return null; }
  }
  // Small bounded JSON parser rejects duplicate keys before the closed decoder.
  function parseSoundJson(text) {
    if (typeof text!=='string' || text.length>12000) throw new Error('sound_response_limit');
    let at=0;
    const ws=()=>{while (/\s/.test(text[at]||'x')) at++;};
    function string() {
      const begin=at++;
      while (at<text.length) { if (text[at]==='\\') { at+=2;continue; } if (text[at++]==='"') return JSON.parse(text.slice(begin,at)); }
      throw new Error('invalid_json');
    }
    function value(depth) {
      if (depth>16) throw new Error('json_depth');ws();
      if (text[at]==='"') return string();
      if (text[at]==='{') {
        at++;ws();const out=Object.create(null);if (text[at]==='}') {at++;return out;}
        for (;;) {ws();if (text[at]!=='"') throw new Error('invalid_json');const key=string();if (Object.prototype.hasOwnProperty.call(out,key)) throw new Error('duplicate_key');ws();if (text[at++]!==':') throw new Error('invalid_json');out[key]=value(depth+1);ws();const token=text[at++];if (token==='}') return out;if (token!==',') throw new Error('invalid_json');}
      }
      if (text[at]==='[') {
        at++;ws();const out=[];if (text[at]===']') {at++;return out;}
        for (;;) {out.push(value(depth+1));ws();const token=text[at++];if (token===']') return out;if (token!==',') throw new Error('invalid_json');}
      }
      const match=/^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.slice(at));
      if (!match) throw new Error('invalid_json');at+=match[0].length;const v=JSON.parse(match[0]);if (typeof v==='number'&&!Number.isFinite(v)) throw new Error('nonfinite');return v;
    }
    const out=value(0);ws();if (at!==text.length) throw new Error('invalid_json');return out;
  }

  const SOUND_LIMIT_TEXT = "This does not establish which sound you said or whether ‘bread’ was said correctly. We haven't checked it against real recordings independently confirmed to use W in place of R.";
  app.sound = {adult:false,optIn:false,declState:'off',decl:null,declGen:0,gen:1,sessionId:cryptoReady?uuid():'unavailable',check:{state:'idle'},result:null,postedCaptureIds:new Set(),paused:false};
  function soundControl(path,body,declaration) {
    // Bound control metadata only; this never carries audio or starts processing.
    if (!declaration) return;
    fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',keepalive:true,headers:{'Content-Type':'application/json',[CSRF_HEADER]:declaration.csrfToken},body:JSON.stringify(body)}).catch(()=>{});
  }
  function resetSound(full=false,text='') {
    const s=app.sound,check=s.check,decl=s.decl;
    s.gen+=1;
    if (check.state==='sending') {
      check.controller.abort();
      if (check.expected) soundControl('/api/sound-cancel',{schemaVersion:1,serverNonce:decl.serverNonce,attemptId:check.expected.attemptId,requestSha256:check.expected.requestSha256,ownership:check.expected.ownership},decl);
      soundControl('/api/sound-reset',{schemaVersion:1,serverNonce:decl.serverNonce,sessionId:s.sessionId,generation:s.gen},decl);
    }
    s.result=null;s.check=text?{state:'stopped',text}:{state:'idle'};
    if (full) {s.adult=false;s.optIn=false;s.decl=null;s.declState='off';s.declGen+=1;}
    if (ui.spTitle) {ui.spTitle.textContent='';ui.spText.textContent='';ui.spLimit.hidden=true;ui.spNext.replaceChildren();ui.spResult.classList.remove('is-result');}
  }
  function soundBread() {
    const p=selectedPrompt();return p && p.id==='r-middle-bread' && GUIDED_CANONICAL_CATALOG.find(p=>p.id==='r-middle-bread').promptSha256===SOUND_CONTRAST.promptSha256 && canonicalJson(p.processingPrompt)===canonicalJson(GUIDED_CANONICAL_CATALOG.find(p=>p.id==='r-middle-bread').processingPrompt);
  }
  // Only a validated declared adult context allows the sound comparison.
  // No choice (null) is not adult, and a child age never is.
  function soundAdultContext(c) { return practiceContextValid(c) && c.kind==='adult'; }
  // `practiceContext` is the snapshot taken when Check sound was chosen.
  function soundCurrent(gen,declGen,take,decl,practiceContext) {
    return gen===app.sound.gen && declGen===app.sound.declGen && app.sound.decl===decl && app.mode==='free' && soundAdultContext(practiceContext) && practiceContextSame(practiceContext,app.practiceContext) && practiceContextSame(take.practiceContext,practiceContext) && app.sound.adult && app.sound.optIn && !app.sound.paused && soundBread() && latestTake()===take && take.setupGen===app.setupGen;
  }
  function soundCheckableTake() {
    const s=app.sound,take=latestTake();
    if (app.mode!=='free' || !soundAdultContext(app.practiceContext) || !soundBread() || !s.adult || !s.optIn || s.paused || s.declState!=='ready' || !s.decl || !s.decl.processingAvailable || !cryptoReady || capturing() || app.check.state==='sending' || s.check.state==='sending' || s.postedCaptureIds.size>=128) return null;
    return take && take.promptId==='r-middle-bread' && take.setupGen===app.setupGen && soundAdultContext(take.practiceContext) && practiceContextSame(take.practiceContext,app.practiceContext) && take.sampleCount>=2400 && take.sampleCount<=64000 && take.wav.length===44+take.sampleCount*2 && !take.soundChecked ? take : null;
  }
  async function soundJson(path,options={}) {
    const res=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',headers:{Accept:'application/json',...options.headers},...options});
    if (res.redirected || res.type!=='basic' || res.status!==200 || !/^application\/json\s*(;|$)/i.test(res.headers.get('Content-Type')||'')) {if(res.body)res.body.cancel().catch(()=>{});throw new Error('sound_transport');}
    return parseSoundJson(new TextDecoder('utf-8',{fatal:true}).decode(await readCapped(res,12000)));
  }
  async function loadSoundDeclaration() {
    const s=app.sound;
    if (!s.adult || !s.optIn || !soundAdultContext(app.practiceContext) || app.mode!=='free' || !soundBread() || s.paused) return;
    const gen=++s.declGen;s.declState='loading';render();
    let d=null;try {d=normalizeSoundDeclaration(await soundJson('/api/sound-declaration'),app.declaration);} catch (_) { /* fail closed */ }
    if(gen!==s.declGen || !s.adult || !s.optIn || app.mode!=='free' || !soundAdultContext(app.practiceContext)) return;
    if (s.decl && d && (canonicalJson(s.decl.binding)!==canonicalJson(d.binding)||s.decl.serverNonce!==d.serverNonce)) {resetSound();clearTakes();}
    s.decl=d;s.declState=d?'ready':'error';render();
  }
  function onSoundAdult() {
    const adult=ui.spAdult.checked && soundAdultContext(app.practiceContext);resetSound(true);cancelCapture('');clearTakes();app.setupGen+=1;
    app.sound.adult=adult;render();announce('Sound comparison settings changed. Record a fresh try after choosing both boxes.');
  }
  function onSoundOptIn() {
    const s=app.sound,optIn=ui.spOptin.checked && s.adult && soundAdultContext(app.practiceContext) && app.mode==='free';
    resetSound();cancelCapture('');clearTakes();app.setupGen+=1;s.optIn=optIn;s.decl=null;s.declState=optIn?'loading':'off';s.declGen+=1;
    render();if(optIn)loadSoundDeclaration();announce(optIn?'Sound comparison is on. Each try is compared only when you choose Check sound.':'Sound comparison is off.');
  }
  function pauseSharedSoundProcessing() {
    app.sound.paused=true;
  }
  async function startSoundCheck() {
    const take=soundCheckableTake(),s=app.sound;
    if (!take || ui.spCheck.dataset.take!==String(take.id)) return;
    take.soundChecked=true;s.postedCaptureIds.add(take.soundCaptureId);
    // Immutable snapshot of the take's adult context; compared again before the POST and before settling.
    const gen=s.gen,declGen=s.declGen,decl=s.decl,prompt=selectedPrompt(),controller=new AbortController(),practiceContext=practiceContextCopy(take.practiceContext);
    const check={state:'sending',takeId:take.id,controller,expected:null};s.check=check;s.result=null;render();announce("Comparing this try's sound.");
    let view;
    try {
      const audio={sha256:await sha256Hex(take.wav),bytes:take.wav.length,sampleCount:take.sampleCount,sampleRateHertz:16000};
      const owner={sessionId:s.sessionId,generation:gen,roundId:'sound-preview',roundKind:'probe',itemId:'r-middle-bread',takeId:String(take.id),captureId:take.soundCaptureId,contextSha256:''};
      const body={schemaVersion:1,attemptId:uuid(),purpose:SOUND_PURPOSE,adultConfirmed:true,optIn:true,practiceMode:'free',selectedChildAge:null,setupGeneration:app.setupGen,serverNonce:decl.serverNonce,promptId:'r-middle-bread',prompt:prompt.processingPrompt,ownership:owner,audio,audioBase64:toBase64(take.wav),binding:decl.binding};
      const context={schemaVersion:1,serverNonce:decl.serverNonce,purpose:SOUND_PURPOSE,adultConfirmed:true,optIn:true,practiceMode:'free',selectedChildAge:null,setupGeneration:body.setupGeneration,sessionId:owner.sessionId,generation:owner.generation,promptId:body.promptId,promptSha256:SOUND_CONTRAST.promptSha256,binding:decl.binding};
      owner.contextSha256=await sha256Hex(encoder.encode(canonicalJson(context)));
      const privateRequest={schemaVersion:1,ownership:owner,audio:{...audio,file:'input.wav'},contrast:SOUND_CONTRAST,sourceSnapshotSha256:SOUND_FIXED_SOURCES.workerSourceSha256};
      const raw=encoder.encode(JSON.stringify(body));
      if(raw.length>MAX_REQUEST_BYTES)throw new Error('sound_request_limit');
      const expected={attemptId:body.attemptId,requestSha256:await sha256Hex(raw),workerRequestSha256:await sha256Hex(encoder.encode(canonicalJson(privateRequest))),ownership:owner,audio,source:decl.binding};
      check.expected=expected;
      if(controller.signal.aborted || !soundCurrent(gen,declGen,take,decl,practiceContext)) return;
      // Ownership is rechecked after every preparation await, immediately before the sole observation POST.
      const data=await soundJson('/api/sound-observation',{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json',[CSRF_HEADER]:decl.csrfToken},body:raw,signal:controller.signal});
      view=interpretSound(data,expected);if(!view)throw new Error('sound_response');
    } catch (_) {view={status:'unavailable',reason:'unverified_reply',modelPreference:null};}
    if (!soundCurrent(gen,declGen,take,decl,practiceContext) || controller.signal.aborted) return;
    if (view.reason==='cleanup_unconfirmed' || view.reason==='processing_unavailable') pauseSharedSoundProcessing();
    s.check={state:'idle'};s.result={takeId:take.id,view};
    const move=document.activeElement===ui.spCancel || document.activeElement===document.body;
    render();if(move)ui.spResult.focus();announce(`Sound comparison: ${ui.spTitle.textContent}.`);
  }
  function onSoundCancel() {resetSound(false,'No result will be shown for this try. The computer may still finish it in the background.');render();ui.record.focus();}
  function soundDisplay(view) {
    if(view.status==='observed_model_preference') {
      const copy={r_path:["Model's best fit: BR",'Of the four tested versions, the experimental sound model fit this recording best to BR, as in “bread”.'],w_path:["Model's best fit: BW",'Of the four tested versions, the experimental sound model fit this recording best to BW.'],other_path:["Model's best fit: another version",'Of the four tested versions, the model fit this recording best to BL or to B followed directly by the rest of the word.']}[view.modelPreference];
      return {title:copy[0],text:copy[1],model:true};
    }
    if(view.status==='inconclusive')return {title:'No clear pick',text:'The model could not tell the tested versions apart for this recording, or the recording did not fit any of them well.',model:true};
    return {title:'No sound comparison result',text:view.reason==='busy'?'The computer was busy with another check, so this try was not compared.':view.reason==='timeout'?'The comparison took too long and was stopped.':view.reason==='unverified_reply'?'The reply could not be verified, so no result is shown.':'The comparison did not finish, so there is no result.'};
  }
  function renderSound() {
    if (!ui.soundPreview) return;
    const s=app.sound;ui.soundPreview.hidden=app.mode!=='free';
    ui.spIneligible.hidden=Boolean(soundBread());ui.spBody.hidden=!soundBread();
    // Child or no choice: both boxes stay off and disabled, and the text points to Who is practicing.
    const adultContext=soundAdultContext(app.practiceContext);
    ui.spAdult.checked=s.adult;ui.spAdult.disabled=capturing()||s.check.state==='sending'||!adultContext;
    ui.spOptin.checked=s.optIn;ui.spOptin.disabled=!s.adult||!adultContext||capturing()||s.check.state==='sending';
    ui.spOptinNote.textContent=s.adult?'Nothing is sent until you choose Check sound for a try. Word check settings are separate.':adultContext?'Tick the box above first.':'Choose Adult (18+) for Who is practicing? first.';
    let display={title:'Sound comparison is off',text:'Tick both boxes below to try it. Nothing is sent until you choose Check sound.'};
    if(!adultContext)display=app.practiceContext===null
      ?{title:'Sound comparison is off',text:'It is for adults only. Choose Adult (18+) for Who is practicing?, above Record, then tick both boxes below before you record.'}
      :{title:'Sound comparison is for adults only',text:'Who is practicing? is set to a child, so it stays off. To use it, choose Adult (18+) above Record; that clears your tries.'};
    else if(s.adult && !s.optIn)display.text='Tick Compare sounds on this computer to turn it on.';
    else if(s.optIn) {
      if(s.declState==='loading')display={title:'',text:'Setting up the sound comparison…'};
      else if(s.declState==='error')display={title:'Sound comparison could not be set up',text:'You can still record, listen and use word check.'};
      else if(!s.decl || !s.decl.processingAvailable || !cryptoReady)display={title:'Sound comparison is not available',text:'It is not available on this computer right now.'};
      else if(capturing())display={title:'',text:'When you stop, you can compare the new try.'};
      else if(s.check.state==='sending')display={title:'Comparing…',text:'This usually takes a few seconds.'};
      else if(s.check.state==='stopped')display={title:'Comparison stopped',text:s.check.text};
      else if(s.result && s.result.takeId===(latestTake()||{}).id)display=soundDisplay(s.result.view);
      else if(soundCheckableTake())display={title:'Ready to compare',text:'Choose Check sound to send this try to the sound model on this computer. Each try can be compared once.'};
      else if(app.check.state==='sending')display={title:'Ready to compare',text:'You can compare this try when the word check finishes.'};
      else display={title:'Sound comparison is on',text:latestTake()?'Record a fresh try to compare again.':'Record a try above, then choose Check sound.'};
    }
    if(s.paused)display={title:'Sound comparison is paused',text:'Processing is paused on this computer until cleanup is checked. You can still record and listen.'};
    ui.spTitle.textContent=display.title;ui.spText.textContent=display.text;ui.spLimit.textContent=SOUND_LIMIT_TEXT;ui.spLimit.hidden=!display.model;ui.spResult.classList.toggle('is-result',Boolean(display.model));ui.spNext.replaceChildren();
    if(s.result && !s.paused)ui.spNext.append(el('li',{text:'To compare again, record a fresh try.'}));
    const take=soundCheckableTake();ui.spCheck.hidden=!take;ui.spCheck.dataset.take=take?String(take.id):'';
    ui.spCancel.hidden=s.check.state!=='sending';ui.spSetupRetry.hidden=s.declState!=='error'||s.paused;
  }

  // ---------- boot ----------

  function boot() {
    for (const id of [
      'word-status', 'word-list', 'catalog-retry', 'cleanup-notice', 'cleanup-reload', 'practice', 'practice-empty',
      'practice-message', 'practice-body', 'word-heading', 'word-position', 'picture', 'picture-missing',
      'example-play', 'example-status', 'record-panel', 'record-word', 'time-fill', 'time-text', 'level-fill', 'record',
      'br-cue', 'br-actions', 'br-example', 'br-take', 'br-record',
      'record-cancel', 'record-status', 'session-note', 'session-count', 'fb-result', 'fb-title', 'fb-text',
      'fb-facts', 'fb-next', 'fb-check', 'fb-cancel', 'fb-setup-retry', 'fb-settings', 'fb-settings-summary',
      'who-field', 'age', 'proc-optin', 'proc-optin-note', 'compare', 'compare-hint', 'compare-example', 'compare-note',
      'takes-clear', 'mirror', 'mouth-outline', 'mirror-placeholder', 'camera-toggle', 'camera-status',
      'visual-optin', 'visual-note', 'visual-status', 'reference',
      'reference-details', 'announcer', 'words',
      'mode-bar', 'mode-free', 'mode-guided',
      'guided-bar', 'guided-phase', 'guided-back', 'guided-end', 'guided-end-confirm', 'guided-end-question',
      'guided-end-yes', 'guided-end-no',
      'guided-start', 'guided-start-heading', 'guided-start-notice', 'guided-age', 'guided-optin',
      'guided-optin-note', 'guided-begin', 'guided-start-status',
      'guided-next', 'guided-skip', 'guided-retention',
      'guided-summary', 'guided-summary-heading', 'guided-summary-context', 'guided-counts',
      'guided-check-counts', 'guided-rows', 'guided-recheck', 'guided-recheck-note',
      'guided-pairs', 'guided-pairs-heading', 'guided-pairs-context', 'guided-pair-count', 'guided-pair-rows',
      'guided-pairs-end',
      'sound-preview','sp-heading','sp-kicker','sp-intro','sp-ineligible','sp-go-bread','sp-body','sp-result','sp-title','sp-text','sp-limit','sp-next','sp-check','sp-cancel','sp-setup-retry','sp-setup','sp-adult','sp-optin','sp-optin-note','sp-about',
      'guided-roster', 'guided-roster-heading', 'guided-roster-list', 'guided-finish', 'guided-finish-note',
    ]) {
      ui[camel(id)] = document.getElementById(id);
    }
    ui.rows = ['a', 'b'].map((slot) => ({
      item: document.getElementById(`try-${slot}`),
      label: document.getElementById(`try-${slot}-label`),
      length: document.getElementById(`try-${slot}-length`),
      result: document.getElementById(`try-${slot}-result`),
      play: document.getElementById(`try-${slot}-play`),
    }));

    ui.picture.addEventListener('error', () => {
      if (!ui.picture.getAttribute('src')) return;
      ui.picture.hidden = true;
      ui.pictureMissing.hidden = false;
    });
    ui.picture.addEventListener('load', () => {
      ui.picture.hidden = false;
      ui.pictureMissing.hidden = true;
    });
    ui.wordList.addEventListener('keydown', onWordListKey);
    ui.catalogRetry.addEventListener('click', loadCatalog);
    ui.cleanupReload.addEventListener('click', () => window.location.reload());
    ui.examplePlay.addEventListener('click', toggleExample);
    ui.compareExample.addEventListener('click', toggleExample);
    ui.brExample.addEventListener('click', onBrExample);
    ui.brTake.addEventListener('click', onBrTake);
    ui.brRecord.addEventListener('click', onBrRecord);
    ui.record.addEventListener('click', onRecordClick);
    ui.recordCancel.addEventListener('click', onRecordCancel);
    for (const row of ui.rows) {
      row.play.addEventListener('click', () => {
        const id = Number(row.play.dataset.take);
        if (Number.isInteger(id) && id > 0) toggleTake(id);
      });
    }
    ui.takesClear.addEventListener('click', onClearTakes);
    ui.cameraToggle.addEventListener('click', onCameraToggle);
    ui.visualOptin.addEventListener('change', () => {
      if (ui.visualOptin.checked) startVisual();
      else stopVisual();
    });
    ui.age.addEventListener('change', onPracticeContextChange);
    ui.procOptin.addEventListener('change', onOptInChange);
    ui.fbCheck.addEventListener('click', startCheck);
    ui.fbCancel.addEventListener('click', onCheckCancel);
    ui.fbSetupRetry.addEventListener('click', loadDeclaration);
    ui.spAdult.addEventListener('change',onSoundAdult);
    ui.spOptin.addEventListener('change',onSoundOptIn);
    ui.spCheck.addEventListener('click',startSoundCheck);
    ui.spCancel.addEventListener('click',onSoundCancel);
    ui.spSetupRetry.addEventListener('click',loadSoundDeclaration);
    ui.spGoBread.addEventListener('click',()=>selectPrompt('r-middle-bread'));

    ui.modeFree.addEventListener('click', onModeFree);
    ui.modeGuided.addEventListener('click', onModeGuided);
    ui.guidedAge.addEventListener('change', onPracticeContextChange);
    ui.guidedOptin.addEventListener('change', onOptInChange);
    ui.guidedBegin.addEventListener('click', onGuidedBegin);
    ui.guidedNext.addEventListener('click', onGuidedNext);
    ui.guidedSkip.addEventListener('click', onGuidedSkip);
    ui.guidedFinish.addEventListener('click', onGuidedFinish);
    ui.guidedRecheck.addEventListener('click', onGuidedRecheck);
    ui.guidedBack.addEventListener('click', onGuidedBack);
    ui.guidedEnd.addEventListener('click', onGuidedEndOpen);
    ui.guidedPairsEnd.addEventListener('click', onGuidedEndOpen);
    ui.guidedEndNo.addEventListener('click', onGuidedEndKeep);
    ui.guidedEndYes.addEventListener('click', onGuidedEndYes);
    ui.guidedEndConfirm.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      onGuidedEndKeep();
    });
    ui.guidedRosterList.addEventListener('keydown', onWordListKey);

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') pauseForBackground();
    });
    window.addEventListener('pagehide', onPageHide);
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) render();
    });

    ui.mirror.muted = true;
    ui.age.value = '';
    ui.procOptin.checked = false;
    ui.guidedAge.value = '';
    ui.guidedOptin.checked = false;
    render();
    loadCatalog();
    loadDeclaration();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
