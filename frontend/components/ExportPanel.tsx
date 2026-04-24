'use client';

import React, { useState } from 'react';
import { Button, Space, App } from 'antd';
import { DownloadOutlined, FileTextOutlined } from '@ant-design/icons';

interface Props {
  documentId: number;
  disabled?: boolean;
}

export default function ExportPanel({ documentId, disabled = false }: Props) {
  const { notification } = App.useApp();
  const [loading, setLoading] = useState<'json' | 'csv' | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const handleExport = async (format: 'json' | 'csv') => {
    setLoading(format);
    try {
      const url = `${apiUrl}/api/v1/documents/${documentId}/export?format=${format}`;
      const res = await fetch(url);

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Export failed' }));
        throw new Error(err.detail);
      }

      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `document_${documentId}_export.${format}`;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
    } catch (err: any) {
      notification.error({
        title: 'Export failed',
        description: err.message || 'Could not export document.',
      });
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="mt-6 pt-6 border-t border-gray-100 dark:border-gray-800">
      <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
        Export Results
      </p>
      <Space>
        <Button
          icon={<FileTextOutlined />}
          loading={loading === 'json'}
          disabled={disabled || loading !== null}
          onClick={() => handleExport('json')}
        >
          Download JSON
        </Button>
        <Button
          icon={<DownloadOutlined />}
          loading={loading === 'csv'}
          disabled={disabled || loading !== null}
          onClick={() => handleExport('csv')}
        >
          Download CSV
        </Button>
      </Space>
    </div>
  );
}
