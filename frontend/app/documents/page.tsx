'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Table, Tag, Button, Space, Empty } from 'antd';
import { EyeOutlined, SyncOutlined } from '@ant-design/icons';
import { Upload } from 'lucide-react';
import api from '@/lib/api';
import type { Document } from '@/lib/types';
import { formatCapacityWaitMessage } from '@/lib/capacityWait';

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(true);

  const fetchDocuments = async () => {
    try {
      // The server scopes the list to this browser's session, taken from
      // the X-Session-Id header that api.ts attaches to every request.
      const res = await api.get('/api/v1/documents');
      setDocuments(res.data.documents || []);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    let interval: NodeJS.Timeout;
    
    if (polling) {
      interval = setInterval(() => {
        fetchDocuments();
      }, 3000); // refresh every 3 seconds
    }
    
    return () => clearInterval(interval);
  }, [polling]);

  const columns = [
    {
      title: 'File Name',
      dataIndex: 'document_url',
      key: 'document_url',
      render: (text: string) => <span className="font-medium text-slate-800 dark:text-slate-200">{text}</span>,
    },
    {
      title: 'Type',
      dataIndex: 'document_type',
      key: 'document_type',
      render: (type: string) => <Tag color="default">{type.toUpperCase()}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string, record: Document) => {
        if (record.waiting_for_capacity) {
          return (
            <Tag color="gold" icon={<SyncOutlined spin />}>
              {formatCapacityWaitMessage(record.capacity_wait_estimated_start).toUpperCase()}
            </Tag>
          );
        }

        let color = 'default';
        if (status === 'completed') color = 'success';
        if (status === 'awaiting_review') color = 'warning';
        if (status === 'processing') color = 'processing';
        if (status === 'failed') color = 'error';

        return (
          <Tag color={color} icon={status === 'processing' ? <SyncOutlined spin /> : null}>
            {status.replace('_', ' ').toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: 'Confidence',
      dataIndex: 'confidence_score',
      key: 'confidence_score',
      render: (score: number) => {
        if (!score && score !== 0) return '-';
        return `${(score * 100).toFixed(0)}%`;
      },
    },
    {
      title: 'Date',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: Document) => (
        <Space size="middle">
          <Link href={`/review/${record.id}`}>
            <Button type="primary" size="small" icon={<EyeOutlined />} ghost>
              Review
            </Button>
          </Link>
        </Space>
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
            Your session
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white">
            Documents
          </h1>
        </div>
        <Button
          type="default"
          icon={<SyncOutlined spin={polling} />}
          onClick={() => setPolling(!polling)}
        >
          {polling ? 'Auto-refresh on' : 'Auto-refresh off'}
        </Button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-white/10 dark:bg-slate-900">
        <Table
          columns={columns}
          dataSource={documents}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 15 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <span className="text-slate-500 dark:text-slate-400">
                    No documents in this session yet.
                  </span>
                }
              >
                <Link
                  href="/#upload"
                  className="inline-flex items-center gap-2 text-sm font-medium !text-amber-700 !underline decoration-amber-400 underline-offset-2 hover:!text-amber-800 dark:!text-amber-400 dark:hover:!text-amber-300"
                >
                  <Upload className="h-3.5 w-3.5" />
                  Upload your first one
                </Link>
              </Empty>
            ),
          }}
        />
      </div>
    </div>
  );
}
