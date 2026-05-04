'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Modal, Input, Button, App, Typography, Progress, Space } from 'antd';
import {
  Zap,
  AlertTriangle,
  Key,
  Mail,
  ExternalLink,
  Sparkles,
  X,
} from 'lucide-react';
import { getSessionId, getUserLlmKey, setUserLlmKey, clearUserLlmKey } from '@/lib/api';
import api from '@/lib/api';

const { Text, Paragraph } = Typography;

interface UsageData {
  used: number;
  limit: number;
  remaining: number;
  reset_seconds: number;
}

/**
 * UsageBanner — shows remaining extractions in the navbar.
 *
 * Displays a compact badge: "7/10 remaining"
 * When limit is hit, opens the LimitModal automatically.
 */
export function UsageBanner() {
  const { notification } = App.useApp();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [hasUserKey, setHasUserKey] = useState(false);

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
    setHasUserKey(!!getUserLlmKey());
    // Refresh usage every 30 seconds
    const interval = setInterval(fetchUsage, 30000);
    return () => clearInterval(interval);
  }, [fetchUsage]);

  const handleSaveKey = () => {
    if (!apiKey.trim() || apiKey.trim().length < 8) {
      notification.warning({
        message: 'Invalid key',
        description: 'Please enter a valid API key (at least 8 characters).',
      });
      return;
    }
    setUserLlmKey(apiKey.trim());
    setHasUserKey(true);
    setApiKey('');
    setModalOpen(false);
    notification.success({
      message: 'API key saved',
      description:
        'Your key is stored in your browser only. Unlimited extractions enabled.',
    });
  };

  const handleClearKey = () => {
    clearUserLlmKey();
    setHasUserKey(false);
    notification.info({
      message: 'Key removed',
      description: 'Back to demo mode with limited extractions.',
    });
  };

  // Format reset time
  const resetHours = usage
    ? Math.ceil(usage.reset_seconds / 3600)
    : 0;

  const pct = usage ? ((usage.remaining / usage.limit) * 100) : 100;
  const isLow = usage ? usage.remaining <= 3 : false;
  const isOut = usage ? usage.remaining <= 0 : false;

  return (
    <>
      {/* Compact badge in navbar */}
      {hasUserKey ? (
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full
            bg-emerald-50 dark:bg-emerald-950/40
            border border-emerald-200 dark:border-emerald-800
            text-emerald-700 dark:text-emerald-300
            text-xs font-medium
            hover:bg-emerald-100 dark:hover:bg-emerald-900/50
            transition-colors cursor-pointer"
        >
          <Key className="w-3 h-3" />
          <span>Own key</span>
        </button>
      ) : usage ? (
        <button
          onClick={() => isOut ? setModalOpen(true) : undefined}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full
            text-xs font-medium transition-colors
            ${isOut
              ? 'bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 cursor-pointer hover:bg-red-100'
              : isLow
                ? 'bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 cursor-default'
                : 'bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 cursor-default'
            }`}
        >
          <Zap className="w-3 h-3" />
          <span>
            {isOut ? 'Limit reached' : `${usage.remaining}/${usage.limit}`}
          </span>
        </button>
      ) : null}

      {/* Limit Modal */}
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
          {isOut && !hasUserKey ? (
            <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-3" />
          ) : (
            <Sparkles className="w-12 h-12 text-indigo-500 mx-auto mb-3" />
          )}

          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
            {hasUserKey
              ? 'API Key Active'
              : isOut
                ? 'Demo Limit Reached'
                : 'Usage & API Key'}
          </h3>

          {!hasUserKey && usage && (
            <div className="mt-4 mb-6">
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
          )}
        </div>

        {/* Section 1: Use your own key */}
        <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 mb-4">
          <div className="flex items-center gap-2 mb-3">
            <Key className="w-4 h-4 text-indigo-500" />
            <Text strong className="text-sm">
              {hasUserKey ? 'Your API Key' : 'Use your own Groq API key'}
            </Text>
          </div>

          {hasUserKey ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <Text className="text-sm text-emerald-700 dark:text-emerald-300">
                    Unlimited extractions active
                  </Text>
                </div>
              </div>
              <Button
                danger
                size="small"
                icon={<X className="w-3 h-3" />}
                onClick={handleClearKey}
              >
                Remove key
              </Button>
              <Paragraph type="secondary" className="text-xs !mb-0">
                Key is stored in your browser only. Never sent to our server for storage.
              </Paragraph>
            </div>
          ) : (
            <div className="space-y-3">
              <Input.Password
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="gsk_..."
                autoComplete="off"
                onPressEnter={handleSaveKey}
              />
              <Button type="primary" block onClick={handleSaveKey}>
                Activate unlimited mode
              </Button>
              <Paragraph type="secondary" className="text-xs !mb-0">
                Get a free key at{' '}
                <a
                  href="https://console.groq.com/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-500 hover:underline inline-flex items-center gap-0.5"
                >
                  console.groq.com
                  <ExternalLink className="w-3 h-3" />
                </a>
                . Stored in your browser only — never on our server.
              </Paragraph>
            </div>
          )}
        </div>

        {/* Section 2: Contact */}
        {!hasUserKey && (
          <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
            <div className="flex items-center gap-2 mb-3">
              <Mail className="w-4 h-4 text-indigo-500" />
              <Text strong className="text-sm">
                Need production access?
              </Text>
            </div>
            <Space direction="vertical" className="w-full" size="small">
              <a
                href="mailto:your-email@example.com"
                className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 hover:text-indigo-500 transition-colors"
              >
                <Mail className="w-4 h-4" />
                your-email@example.com
              </a>
              <a
                href="https://www.upwork.com"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 hover:text-indigo-500 transition-colors"
              >
                <ExternalLink className="w-4 h-4" />
                Hire me on Upwork
              </a>
            </Space>
          </div>
        )}
      </Modal>
    </>
  );
}
