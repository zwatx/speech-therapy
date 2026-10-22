"""Prospective evidence requirements, not a collection or analysis protocol."""

from workbench.domain import semantic_digest

from .packet import validate_packet


def validation_draft(packet):
    validate_packet(packet)
    return {
        'schemaVersion': 1, 'kind': 'prospective-validation-declaration',
        'status': 'proposed_not_final_not_collected',
        'sourcePackSha256': packet['sourcePackSha256'],
        'packetSha256': semantic_digest(packet),
        'scope': {'ageRange': [6, 12], 'language': 'en',
                  'task': 'pending qualified consonant-target task definition'},
        'pendingDecisions': dict.fromkeys([
            'qualifiedTaskAndReferenceRecord', 'referenceVariety',
            'identityAndHouseholdLinkage', 'recruitmentAndConsentPermission',
            'referenceAndIllustrationRights', 'retentionAndWithdrawalPolicy',
            'sampleSizeAndPrecisionRationale', 'acceptanceThresholds',
            'deploymentAndAccessDesign', 'reviewedCorrectionAndCuePolicy',
        ]),
        'evidenceRequirements': [
            {'id': 'independent_reference', 'required': [
                'Independent qualified hearing against the controlled task definition.',
                'Separate speech presence, intended prompt match, pronunciation variant, target occurrence and recording quality.',
                'Blinded original reviews, unavailable markers, disagreement and adjudication history; prediction access controlled separately.',
            ]},
            {'id': 'all_attempt_denominator', 'required': [
                'Log every initiated attempt before admission or permission results, including cancelled, rejected, unavailable and withdrawn attempts.',
                'Declare terminal states and reasons; report abstention, capture, prompt and reference coverage alongside admitted results.',
                'Preserve retry ancestry without counting retries as independent people or silently excluding failures.',
            ]},
            {'id': 'split_isolation', 'required': [
                'Declare participant, household and normalized source-word linkage across all data sources before fitting or evaluation.',
                'Report joint linkage components, conflicts and giant connected groups; speaker/household/word isolation may be infeasible.',
                'If isolation is infeasible, declare a revised estimand and prospective split policy before execution; do not quietly weaken isolation.',
                'Keep any reserved study separate and sealed unless a new concrete authorization and protocol permit opening it.',
            ]},
            {'id': 'repeat_and_conditions', 'required': [
                'Distinguish planned repeat measurements from same-setup capture retries; retain order, interval and prompt ancestry.',
                'Declare device, environment, assistance and acquisition conditions, with age and language-variety strata.',
                'Estimate repeatability and meaningful change under the declared conditions; participation counts are not improvement.',
            ]},
            {'id': 'precision_and_correction', 'required': [
                'Justify prospective participant and rare-stratum coverage using feasibility and clustered uncertainty, not token count alone.',
                'Declare accuracy and abstention estimands, subgroup coverage, false corrections and reference disagreement.',
                'Predeclare acceptance thresholds and meaningful-change criteria after qualified task/reference decisions; no borrowed /r/ thresholds.',
                'Validate prompt admission and correction safety in the intended app domain before any learner-facing findings or cues.',
            ]},
        ],
        'claimLimits': dict(packet['claimLimits']),
        'meaning': 'Requirements for a future declared validation protocol; no participants, references, sample-size calculation or clinical validation established',
    }
