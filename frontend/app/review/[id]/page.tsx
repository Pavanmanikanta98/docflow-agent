'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Card, Typography, Spin, App, Button, Modal, Input } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import api from '@/lib/api';
import ExtractionReview from '@/components/ExtractionReview';
import ExportPanel from '@/components/ExportPanel';
import type { Document } from '@/lib/types';

const { Title } = Typography;

/** Shows the PDF in an iframe. If bytes are gone (cleared post-processing), shows a clean message. */
function FilePreview({ fileUrl, filename }: { fileUrl: string; filename: string }) {
  const [available, setAvailable] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    fetch(fileUrl, { method: 'HEAD' })
      .then((r) => setAvailable(r.ok))
      .catch(() => setAvailable(false));
  }, [fileUrl]);

  if (available === null) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        <span>Loading preview…</span>
      </div>
    );
  }

  if (!available) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center p-8">
        <div className="text-5xl opacity-30">📄</div>
        <p className="font-semibold text-gray-600 dark:text-gray-300">{filename}</p>
        <p className="text-sm text-gray-400 dark:text-gray-500 max-w-xs">
          File preview is not available. As per our privacy policy, uploaded documents are
          processed in-memory and cleared immediately after extraction.
        </p>
      </div>
    );
  }

  return (
    <iframe
      src={fileUrl}
      className="w-full flex-1 border-0 min-h-[500px]"
      title="Document Preview"
    />
  );
}



export default function ReviewPage() {
  const { id } = useParams();
  const router = useRouter();
  const { notification } = App.useApp();
  const [doc, setDoc] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const fileUrl = `${apiUrl}/api/v1/documents/${id}/file`;

  useEffect(() => {
    if (!id) return;
    api.get(`/api/v1/documents/${id}`)
      .then((res) => setDoc(res.data))
      .catch(() => notification.error({ title: 'Failed to load document.' }))
      .finally(() => setLoading(false));
  }, [id]);

  const submitReview = async (status: 'approved' | 'rejected', reason?: string) => {
    setSubmitting(true);
    try {
      await api.post(`/api/v1/documents/${id}/review`, {
        job_id: String(id),
        human_review_status: status,
        human_review_rejection_reason: reason ?? null,
        review_comments: 'Reviewed via DocFlow dashboard',
      });
      notification.success({ title: `Document ${status}` });
      router.push('/documents');
    } catch {
      notification.error({ title: 'Failed to submit review.' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleRejectConfirm = async () => {
    if (!rejectReason.trim()) return;
    setRejectModalOpen(false);
    await submitReview('rejected', rejectReason.trim());
    setRejectReason('');
  };

  if (loading) return <div className="flex justify-center items-center h-96"><Spin size="large" /></div>;
  if (!doc) return <div className="text-center text-red-500 mt-20">Document not found.</div>;

  return (
    <div className="flex flex-col gap-4">

      {/* Reject reason modal */}
      <Modal
        title="Reason for Rejection"
        open={rejectModalOpen}
        onCancel={() => setRejectModalOpen(false)}
        onOk={handleRejectConfirm}
        okText="Confirm Rejection"
        okButtonProps={{ danger: true, loading: submitting, disabled: !rejectReason.trim() }}
      >
        <div className="py-3">
          <p className="text-sm text-gray-500 mb-3">
            This document will remain in <strong>awaiting review</strong> so it can be re-reviewed after corrections.
          </p>
          <Input.TextArea
            rows={3}
            placeholder="e.g. Vendor name incorrect, invoice date missing…"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            autoFocus
          />
        </div>
      </Modal>

      {/* Page header with back nav */}
      <div className="flex items-center gap-3">
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => router.push('/documents')}
        >
          Back to Documents
        </Button>
        <span className="text-gray-400 dark:text-gray-500 text-sm">
          {doc.document_url} · #{doc.id}
        </span>
      </div>

      {/* Main split layout */}
      <div className="flex flex-col lg:flex-row gap-6" style={{ height: 'calc(100vh - 180px)' }}>

      {/* Left — native PDF preview (only available immediately after upload, cleared after processing) */}
      <Card
        className="flex-1 overflow-hidden shadow-sm bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 flex flex-col"
        styles={{ body: { padding: 0, flex: 1, display: 'flex', flexDirection: 'column' } }}
      >
        <FilePreview fileUrl={fileUrl} filename={doc.document_url} />
      </Card>

      {/* Right — review + export */}
      <Card className="w-full lg:w-[450px] overflow-y-auto shadow-sm bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm border-gray-200 dark:border-gray-800">
        <Title level={4} className="!mb-6">Extraction Results</Title>

        <ExtractionReview
          doc={doc}
          submitting={submitting}
          onApprove={() => submitReview('approved')}
          onReject={() => setRejectModalOpen(true)}
        />

        {doc.status === 'completed' && (
          <ExportPanel documentId={doc.id} />
        )}
      </Card>

      </div>
    </div>
  );
}
