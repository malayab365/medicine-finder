// Mirrors the FastAPI response models in backend/app/schemas.py.

export interface Label {
  indications: string | null;
  dosage: string | null;
  warnings: string | null;
  adverse_reactions: string | null;
}

export interface AdverseEvent {
  term: string;
  count: number;
}

export interface NameSearchResponse {
  query: string;
  matched_name: string | null;
  rxcui: string | null;
  label: Label | null;
  adverse_events: AdverseEvent[];
  disclaimer: string;
}

export interface Candidate {
  name: string;
  matched_name: string | null;
  rxcui: string | null;
  label: Label | null;
}

export interface SymptomSearchResponse {
  emergency: boolean;
  message: string | null;
  candidates: Candidate[];
  disclaimer: string;
}

export interface User {
  id: number;
  username: string;
}

// Label fields rendered as cards, in display order.
export const LABEL_FIELDS: [keyof Label, string][] = [
  ["indications", "Uses"],
  ["dosage", "Dosage"],
  ["warnings", "Warnings"],
  ["adverse_reactions", "Side effects"],
];
