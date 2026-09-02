'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Modal, Typography, Progress, Space } from 'antd';
import {
  Zap,
  AlertTriangle,
  Mail,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { getSessionId } from '@/lib/api';
import api from '@/lib/api';

const { Text } = Typography;

interface UsageData {
  used: number;
  limit: number;
  remaining: number;
  reset_seconds: number;
}

const CONTACT_EMAIL =
  process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? 'contact@yourdomain.com';
const UPWORK_URL =
  process.env.NEXT_PUBLIC_UPWORK_URL ?? 'https://www.upwork.com';

/**
 * UsageBanner — read-only usage badge in the navbar.
 *
 * Shows "7/10" remaining, opens a contact-only modal on click.
 * No API-key paste UI — production access goes through email/Upwork.
 */
export function UsageBanner() {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const fetchUsage = useCallback(async () => {
    try {
      const sessionId = getSessionId();
      const { data } = await api.get(`/api/v1/usage?session_id=${sessionId}`);
      setUsage(data);
    } catch {
      // Silently fail — badge just won't show
    }
  }, []);

  useEffect(() => {
    fetchUsage();
    const interval = setInterval(fetchUsage, 30000);
    return () => clearInterval(interval);
  }, [fetchUsage]);

  const resetHours = usage ? Math.ceil(usage.reset_seconds / 3600) : 0;
  const pct = usage ? (usage.remaining / usage.limit) * 100 : 100;
  const isLow = usage ? usage.remaining <= 3 : false;
  const isOut = usage ? usage.remaining <= 0 : false;

  if (!usage) return null;

  return (
    <>
      <button
        onClick={() => setModalOpen(true)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full
          text-xs font-medium transition-colors
          ${isOut
            ? 'bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 cursor-pointer hover:bg-red-100'
            : isLow
              ? 'bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 cursor-pointer hover:bg-amber-100'
              : 'bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 cursor-pointer hover:bg-slate-100'
          }`}
      >
        <Zap className="w-3 h-3" />
        <span>{isOut ? 'Limit reached' : `${usage.remaining}/${usage.limit}`}</span>
      </button>

      <Modal
        title={null}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        width={480}
        destroyOnClose
        centered
      >
        <div className="text-center pt-2 pb-4">
          {isOut ? (
            <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-3" />
          ) : (
            <Sparkles className="w-12 h-12 text-indigo-500 mx-auto mb-3" />
          )}

          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
            {isOut ? 'Demo Limit Reached' : 'Demo Usage'}
          </h3>

          <div className="mt-4 mb-2">
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>{usage.used} used</span>
              <span>{usage.remaining} remaining</span>
            </div>
            <Progress
              percent={100 - pct}
              showInfo={false}
              strokeColor={isOut ? '#ef4444' : isLow ? '#f59e0b' : '#6366f1'}
              trailColor="rgba(0,0,0,0.06)"
              size="small"
            />
            <Text type="secondary" className="text-xs mt-1 block">
              Resets in ~{resetHours}h (UTC midnight)
            </Text>
          </div>
        </div>

        <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
          <div className="flex items-center gap-2 mb-3">
            <Mail className="w-4 h-4 text-indigo-500" />
            <Text strong className="text-sm">
              Need production access?
            </Text>
          </div>
          <Text type="secondary" className="text-xs block mb-3">
            The demo runs on a shared free tier. For higher volume or a
            production-ready deployment, get in touch.
          </Text>
          <Space direction="vertical" className="w-full" size="small">
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 hover:text-indigo-500 transition-colors"
            >
              <Mail className="w-4 h-4" />
              {CONTACT_EMAIL}
            </a>
            <a
              href={UPWORK_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 hover:text-indigo-500 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              Hire me on Upwork
            </a>
          </Space>
        </div>
      </Modal>
    </>
  );
}
