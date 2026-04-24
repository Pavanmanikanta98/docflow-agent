'use client';

import { useState } from 'react';
import { Upload } from 'antd';
import type { UploadProps } from 'antd';
import { CloudUpload, Loader2 } from 'lucide-react';

const { Dragger } = Upload;

interface DropZoneProps {
  accept?: string;
  disabled?: boolean;
  uploading?: boolean;
  customRequest: NonNullable<UploadProps['customRequest']>;
}

export function DropZone({
  accept = '.pdf,.png,.jpg,.jpeg',
  disabled = false,
  uploading = false,
  customRequest,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false);

  const isDisabled = disabled || uploading;

  return (
    <div className="docflow-dropzone">
      <Dragger
        accept={accept}
        multiple={false}
        showUploadList={false}
        customRequest={customRequest}
        disabled={isDisabled}
        onDrop={() => setDragging(false)}
      >
        <div
          onDragEnter={() => !isDisabled && setDragging(true)}
          onDragLeave={() => setDragging(false)}
          className={[
            'rounded-xl border-2 border-dashed p-12 transition-all duration-200',
            'flex flex-col items-center gap-4 select-none',
            isDisabled
              ? 'opacity-50 cursor-not-allowed'
              : 'cursor-pointer',
            dragging
              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30 scale-[1.01]'
              : 'border-slate-200 dark:border-slate-700 hover:border-indigo-400 dark:hover:border-indigo-600 hover:bg-slate-50/60 dark:hover:bg-slate-800/30',
          ].join(' ')}
        >
          {uploading ? (
            <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
          ) : (
            <CloudUpload
              className={[
                'w-10 h-10 transition-colors duration-200',
                dragging
                  ? 'text-indigo-500'
                  : 'text-slate-400 dark:text-slate-500',
              ].join(' ')}
            />
          )}

          <div className="text-center">
            <p className="font-semibold text-slate-700 dark:text-slate-300">
              {uploading ? 'Uploading…' : 'Drop your document here'}
            </p>
            {!uploading && (
              <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">
                or{' '}
                <span className="text-indigo-600 dark:text-indigo-400 font-medium underline underline-offset-2">
                  browse files
                </span>
              </p>
            )}
          </div>

          <span className="text-xs text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-full">
            PDF · PNG · JPG — up to 10 MB
          </span>
        </div>
      </Dragger>
    </div>
  );
}
