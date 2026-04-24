'use client';

import React, { useEffect } from 'react';
import { Form, Input, Button, Alert, Tag, Typography } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import type { Document } from '@/lib/types';

const { Text } = Typography;

interface Props {
  doc: Document;
  onApprove: () => void;
  onReject: () => void;
  submitting: boolean;
}

/** Keys we store internally — never show as form fields */
const INTERNAL_KEYS = new Set(['_field_confidences', 'confidence_score']);

function valueToString(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function ExtractionReview({ doc, onApprove, onReject, submitting }: Props) {
  const [form] = Form.useForm();
  const results = (doc.extraction_results ?? {}) as Record<string, unknown>;
  const fieldConfidences = (results['_field_confidences'] ?? {}) as Record<string, number>;

  // Set form values after mount (initialValues only works on first render)
  useEffect(() => {
    const values: Record<string, string> = {};
    Object.keys(results).forEach((key) => {
      if (INTERNAL_KEYS.has(key)) return;
      values[key] = valueToString(results[key]);
    });
    form.setFieldsValue(values);
  }, [form, results]);

  const visibleKeys = Object.keys(results).filter((k) => !INTERNAL_KEYS.has(k));

  if (visibleKeys.length === 0) {
    return (
      <Alert
        type="info"
        showIcon
        title="No extraction results yet or processing failed."
      />
    );
  }

  return (
    <Form layout="vertical" form={form}>
      {/* Status + confidence summary */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <Tag color="cyan">{doc.document_type.toUpperCase()}</Tag>
        <Tag color={doc.confidence_score != null && doc.confidence_score >= 0.75 ? 'success' : 'warning'}>
          {doc.confidence_score != null
            ? `Confidence: ${(doc.confidence_score * 100).toFixed(0)}%`
            : 'No score yet'}
        </Tag>
      </div>

      {visibleKeys.map((key) => {
        const confidence = fieldConfidences[key] ?? 1;
        const lowConfidence = confidence < 0.75;
        const value = results[key];
        const isMultiline = Array.isArray(value) || (typeof value === 'string' && value.length > 80);

        return (
          <Form.Item
            key={key}
            name={key}
            label={
              <span className="flex justify-between w-full">
                <span className="capitalize font-medium">{key.replace(/_/g, ' ')}</span>
                {lowConfidence && (
                  <Text type="danger" className="text-xs ml-2">
                    ⚠ {(confidence * 100).toFixed(0)}% confidence
                  </Text>
                )}
              </span>
            }
            className="mb-4"
          >
            {isMultiline ? (
              <Input.TextArea
                rows={3}
                className={lowConfidence ? 'border-red-400' : ''}
              />
            ) : (
              <Input
                size="large"
                className={lowConfidence ? 'border-red-400' : ''}
              />
            )}
          </Form.Item>
        );
      })}

      {/* Actions */}
      <div className="flex gap-3 mt-6">
        <Button
          type="primary"
          size="large"
          icon={<CheckCircleOutlined />}
          className="flex-1 bg-green-600 border-none hover:!bg-green-700"
          loading={submitting}
          onClick={onApprove}
        >
          Approve
        </Button>
        <Button
          danger
          size="large"
          icon={<CloseCircleOutlined />}
          className="flex-1"
          loading={submitting}
          onClick={() => onReject()}
        >
          Reject
        </Button>
      </div>
    </Form>
  );
}
