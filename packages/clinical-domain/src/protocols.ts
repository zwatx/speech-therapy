import type {
  TargetProtocol,
  TargetProtocolId,
  TargetProtocolRegistry,
} from "./types.ts";

export const targetProtocolRegistryVersion = "foundation-v1";

export const targetProtocols: Record<TargetProtocolId, TargetProtocol> = {
  "bilabial-closure-v1": {
    id: "bilabial-closure-v1",
    label: "Bilabial closure",
    phonemes: ["p", "b", "m"],
    status: "candidate",
    visualCue: "bilabial-closure",
  },
  "labiodental-contact-v1": {
    id: "labiodental-contact-v1",
    label: "Lip and front-teeth relationship",
    phonemes: ["f", "v"],
    status: "candidate",
    visualCue: "labiodental-contact",
  },
  "interdental-visibility-v1": {
    id: "interdental-visibility-v1",
    label: "Tongue-tip visibility",
    phonemes: ["θ", "ð"],
    status: "candidate",
    visualCue: "interdental-visibility",
  },
  "l-tip-lift-research-v1": {
    id: "l-tip-lift-research-v1",
    label: "Tongue-tip lift research",
    phonemes: ["l"],
    status: "research",
    visualCue: "tongue-tip-lift",
  },
  "audio-only-v1": {
    id: "audio-only-v1",
    label: "Audio-only targets",
    phonemes: ["s", "z", "ʃ", "tʃ", "r", "k", "g", "ŋ"],
    status: "audio-only",
    visualCue: null,
  },
};

export const targetProtocolRegistry: TargetProtocolRegistry = {
  version: targetProtocolRegistryVersion,
  protocols: targetProtocols,
};

export function getTargetProtocol(id: TargetProtocolId): TargetProtocol {
  return targetProtocols[id];
}
