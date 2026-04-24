/** Shared TypeScript types for DocFlow frontend. */

export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'awaiting_review';

export type DocumentType = 'invoice' | 'contract';

export interface ExtractionField {
  value: string | number | null;
  confidence: number;
  needs_review: boolean;
}

export interface ExtractionResult {
  [key: string]: ExtractionField | string | number | null;
}

export interface Document {
  id: number;
  tenant_id: string;
  document_type: DocumentType;
  document_url: string;
  document_size: number;
  document_mime_type: string;
  status: DocumentStatus;
  extraction_results: ExtractionResult | null;
  confidence_score: number | null;
  human_review_required: boolean | null;
  human_review_comments: string | null;
  human_review_status: 'approved' | 'rejected' | null;
  human_review_rejection_reason: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface DocumentListResponse {
  documents: Document[];
  total: number;
  page: number;
  page_size: number;
}
