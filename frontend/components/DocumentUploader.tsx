'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Select, Card, App } from 'antd';
import { FileText } from 'lucide-react';
import type { UploadProps } from 'antd';
import api from '@/lib/api';
import type { DocumentType } from '@/lib/types';
import { DropZone } from '@/components/common/DropZone';

interface DocumentUploaderProps {
  variant?: 'default' | 'embedded';
}

export default function DocumentUploader({
  variant = 'default',
}: DocumentUploaderProps) {
  const router = useRouter();
  const { notification } = App.useApp();
  const [docType, setDocType] = useState<DocumentType>('invoice');
  const [uploading, setUploading] = useState(false);

  const customRequest: NonNullable<UploadProps['customRequest']> = async (options) => {
    const { file, onSuccess, onError } = options;
    setUploading(true);

    const formData = new FormData();
    formData.append('file', file as Blob);
    formData.append('document_type', docType);
    formData.append('tenant_id', 'demo-tenant-id');

    try {
      const { data } = await api.post('/api/v1/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onSuccess?.(data, file as unknown as XMLHttpRequest);
      notification.success({
        title: 'Uploaded',
        description: 'Document queued for extraction.',
      });
      router.push('/documents');
    } catch (err: unknown) {
      onError?.(err as Error);
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      notification.error({
        title: 'Upload failed',
        description: detail || 'Something went wrong.',
      });
    } finally {
      setUploading(false);
    }
  };

  const content = (
    <>
      <div className="mb-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <span className="font-semibold text-sm flex items-center gap-2 text-slate-700 dark:text-slate-300">
          <FileText className="w-4 h-4 text-indigo-500" />
          Document Type
        </span>
        <Select
          value={docType}
          onChange={(v) => setDocType(v as DocumentType)}
          options={[
            { value: 'invoice', label: 'Invoice' },
            { value: 'contract', label: 'Contract' },
          ]}
          className="w-full sm:w-44"
          size="large"
          disabled={uploading}
        />
      </div>

      <DropZone
        customRequest={customRequest}
        uploading={uploading}
        accept=".pdf,.png,.jpg,.jpeg"
      />
    </>
  );

  if (variant === 'embedded') {
    return content;
  }

  return (
    <Card className="shadow-sm border border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/60 backdrop-blur-sm">
      {content}
    </Card>
  );
}
