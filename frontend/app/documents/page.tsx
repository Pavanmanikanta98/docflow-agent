'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Table, Tag, Typography, Button, Space } from 'antd';
import { EyeOutlined, SyncOutlined } from '@ant-design/icons';
import api from '@/lib/api';
import type { Document } from '@/lib/types';

const { Title } = Typography;

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(true);

  const fetchDocuments = async () => {
    try {
      // Hardcoding default tenant as 'demo-tenant-id' matching upload form
      // In prod, this passes the api key in header as configured in api.ts
      const res = await api.get('/api/v1/documents?tenant_id=demo-tenant-id');
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
      render: (text: string) => <span className="font-medium text-indigo-600 dark:text-indigo-400">{text}</span>,
    },
    {
      title: 'Type',
      dataIndex: 'document_type',
      key: 'document_type',
      render: (type: string) => <Tag color="blue">{type.toUpperCase()}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
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
    <div className="max-w-6xl mx-auto shadow-sm p-6 bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-6">
        <Title level={3} className="!m-0">Documents</Title>
        <Button 
          type="default" 
          icon={<SyncOutlined spin={polling} />} 
          onClick={() => setPolling(!polling)}
        >
          {polling ? 'Auto-refresh On' : 'Auto-refresh Off'}
        </Button>
      </div>

      <Table 
        columns={columns} 
        dataSource={documents} 
        rowKey="id" 
        loading={loading}
        pagination={{ pageSize: 15 }}
      />
    </div>
  );
}
