import clsx from "clsx";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, getErrorMessage } from "../lib/api";
import { showApiError, toast } from "../lib/toast";
import { useDebouncedValue } from "../lib/use-debounced-value";
import {
  btnPrimaryClass,
  btnSecondaryClass,
  inputClass,
  inputMonoClass,
  labelClass,
  selectClass,
  tdClass,
  thClass,
} from "../lib/styles";
import { useDocumentTitle } from "../lib/use-document-title";
import { useUiStore } from "../stores/uiStore";
import type {
  IProjectListResponse,
  ISecretListResponse,
  ISecretOut,
} from "../types/api";
import CopyButton from "../components/CopyButton";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import { SkeletonTableRows } from "../components/Skeleton";


const PAGE_SIZE = 50;

// Inline value editor component
function InlineValueCell({ 
  secretId, 
  hasValue, 
  onSave 
}: { 
  secretId: string; 
  hasValue: boolean;
  onSave: (id: string, value: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEditing = () => {
    setDraft("");
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const save = async () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(secretId, trimmed);
      setEditing(false);
      setDraft("");
    } catch {
      // Error handled by parent
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void save();
    } else if (e.key === "Escape") {
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input
          ref={inputRef}
          type="password"
          className="w-32 rounded border border-blue-300 bg-white px-1.5 py-0.5 font-mono text-xs text-neutral-900 outline-none focus:ring-1 focus:ring-blue-400"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => { if (!saving) void save(); }}
          onKeyDown={handleKeyDown}
          disabled={saving}
          placeholder="输入新值"
        />
        {saving && (
          <span className="shrink-0 text-[10px] text-neutral-400">保存中…</span>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {hasValue ? (
        <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
          已填写
        </span>
      ) : (
        <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-600">
          待填写
        </span>
      )}
      <button
        type="button"
        className="text-neutral-400 hover:text-blue-600"
        onClick={startEditing}
        title={hasValue ? "覆盖写入" : "点击填写"}
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
        </svg>
      </button>
    </div>
  );
}

export default function SecretsPage() {
  useDocumentTitle("加密密钥");
  const queryClient = useQueryClient();
  const activeProjectId = useUiStore((s) => s.activeProjectId);
  const isAdmin = useUiStore((s) => s.vaultRole) === "admin";

  const [searchInput, setSearchInput] = useState("");
  const searchDebounced = useDebouncedValue(searchInput);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [page, setPage] = useState(0);

  // Reset page when filters change
  useEffect(() => {
    setPage(0);
  }, [activeProjectId, searchDebounced, categoryFilter]);

  const listUrl = useMemo(
    () => {
      const params = new URLSearchParams();
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(page * PAGE_SIZE));
      if (activeProjectId) params.set("project_id", activeProjectId);
      if (searchDebounced?.trim()) params.set("q", searchDebounced.trim());
      if (categoryFilter?.trim()) params.set("category", categoryFilter.trim());
      return `/api/secrets?${params.toString()}`;
    },
    [activeProjectId, searchDebounced, categoryFilter, page],
  );

  const listQuery = useQuery({
    queryKey: ["secrets", listUrl],
    queryFn: () => apiRequest<ISecretListResponse>(listUrl),
  });

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiRequest<IProjectListResponse>("/api/projects?limit=200"),
  });

  const [showAdd, setShowAdd] = useState(false);
  const [addKey, setAddKey] = useState("");
  const [addValue, setAddValue] = useState("");
  const [addEnabled, setAddEnabled] = useState(true);
  const [addBaseUrl, setAddBaseUrl] = useState("");
  const [addCategory, setAddCategory] = useState("");
  const [addProjectId, setAddProjectId] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (body: {
      key: string;
      value: string;
      project_id: string | null;
      enabled: boolean;
      base_url: string | null;
      category: string | null;
    }) =>
      apiRequest<ISecretOut>("/api/secrets", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["secrets"] });
      closeAdd();
      toast.success("密钥已创建。");
    },
    onError: (e: Error) => {
      setAddError(e.message);
      showApiError(e);
    },
  });

  const handleInlineSave = async (id: string, value: string) => {
    try {
      await apiRequest<ISecretOut>(`/api/secrets/${id}/rotate`, {
        method: "POST",
        body: JSON.stringify({ value }),
      });
      void queryClient.invalidateQueries({ queryKey: ["secrets"] });
      toast.success("密钥已覆盖写入。");
    } catch (e) {
      showApiError(e instanceof Error ? e : new Error("保存失败"));
      throw e;
    }
  };

  const closeAdd = () => {
    setShowAdd(false);
    setAddError(null);
  };

  const openAdd = () => {
    setAddKey("");
    setAddValue("");
    setAddEnabled(true);
    setAddBaseUrl("");
    setAddCategory("");
    setAddProjectId(activeProjectId);
    setAddError(null);
    setShowAdd(true);
  };

  const onSubmitAdd = (e: FormEvent) => {
    e.preventDefault();
    const key = addKey.trim();
    const value = addValue;
    if (!key || !value) {
      setAddError("键和值为必填项。");
      return;
    }
    createMutation.mutate({
      key,
      value,
      project_id: addProjectId,
      enabled: addEnabled,
      base_url: addBaseUrl.trim() || null,
      category: addCategory.trim() || null,
    });
  };

  const items = listQuery.data?.items ?? [];
  const projectOptions = projectsQuery.data?.items ?? [];

  return (
    <div className="p-8">
      <PageHeader
        title="加密密钥"
        description="密钥以只写模式管理，已存值不可查看。编辑时输入新值即可覆写。"
        action={isAdmin ? (
          <button type="button" onClick={openAdd} className={btnPrimaryClass}>
            添加密钥
          </button>
        ) : undefined}
      />

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="sec-search" className="block text-xs font-medium text-neutral-600">
            搜索
          </label>
          <input
            id="sec-search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className={`mt-1 w-64 ${inputMonoClass}`}
            placeholder="Key\u2026"
            autoComplete="off"
          />
        </div>
        <div>
          <label htmlFor="sec-cat" className="block text-xs font-medium text-neutral-600">
            分类
          </label>
          <input
            id="sec-cat"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className={`mt-1 w-48 ${inputClass}`}
            placeholder="Filter\u2026"
            autoComplete="off"
          />
        </div>
      </div>

      {listQuery.error ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {getErrorMessage(listQuery.error)}
        </p>
      ) : null}

      {!listQuery.isLoading && items.length > 0 ? (
        <p className="mt-6 text-xs text-neutral-500">共 {listQuery.data?.total ?? items.length} 条</p>
      ) : null}
      <div className={`${items.length > 0 ? "mt-2" : "mt-6"} overflow-x-auto`}>
        <table className="w-full border-collapse text-sm">
          <thead className="bg-neutral-100">
            <tr>
              <th className={thClass}>
                键
              </th>
              <th className={thClass}>
                值
              </th>
              <th className={thClass}>
                启用
              </th>
              <th className={thClass}>
                分类
              </th>
              <th className={thClass}>
                轮换时间
              </th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading ? (
              <SkeletonTableRows cols={5} rows={3} />
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} className="border border-neutral-200 p-0">
                  <EmptyState
                    title="未找到密钥"
                    description="没有匹配当前筛选条件的密钥。请调整搜索条件或添加新密钥。"
                    action={isAdmin ? (
                      <button type="button" onClick={openAdd} className={btnPrimaryClass}>
                        添加密钥
                      </button>
                    ) : undefined}
                  />
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="transition-colors hover:bg-neutral-50">
                  <td className={`${tdClass} font-mono text-neutral-900`}>
                    <span className="inline-flex items-center">
                      {row.key}
                      <CopyButton text={row.key} />
                    </span>
                  </td>
                  <td className={tdClass}>
                    <InlineValueCell 
                      secretId={row.id} 
                      hasValue={row.has_value ?? false} 
                      onSave={handleInlineSave}
                    />
                  </td>
                  <td className={tdClass}>
                    <span
                      className={clsx(
                        "rounded-md px-2 py-0.5 text-xs font-medium",
                        row.enabled
                          ? "bg-emerald-100 text-emerald-900"
                          : "bg-neutral-200 text-neutral-600",
                      )}
                    >
                      {row.enabled ? "是" : "否"}
                    </span>
                  </td>
                  <td className={`${tdClass} text-neutral-700`}>
                    {row.category ?? "\u2014"}
                  </td>
                  <td className={`${tdClass} whitespace-nowrap text-neutral-600`}>
                    {row.rotated_at ? new Date(row.rotated_at).toLocaleString() : "\u2014"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {listQuery.data && listQuery.data.total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <p className="text-neutral-500">
            显示 {page * PAGE_SIZE + 1} - {Math.min((page + 1) * PAGE_SIZE, listQuery.data.total)} / 共 {listQuery.data.total} 条
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-neutral-700 transition-colors hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              上一页
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={(page + 1) * PAGE_SIZE >= listQuery.data.total}
              className="rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-neutral-700 transition-colors hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      )}

      <Modal open={showAdd} onClose={closeAdd} title="新建密钥" titleId="secret-add-title">
        <form onSubmit={onSubmitAdd} className="mt-4 space-y-3">
          <div>
            <label className={labelClass} htmlFor="s-key">键</label>
            <input id="s-key" value={addKey} onChange={(e) => setAddKey(e.target.value)} className={`mt-1 ${inputMonoClass}`} />
          </div>
          <div>
            <label className={labelClass} htmlFor="s-val">值</label>
            <textarea id="s-val" value={addValue} onChange={(e) => setAddValue(e.target.value)} rows={3} className={`mt-1 ${inputMonoClass}`} />
          </div>
          <div className="flex items-center gap-2">
            <input id="s-en" type="checkbox" checked={addEnabled} onChange={(e) => setAddEnabled(e.target.checked)} />
            <label htmlFor="s-en" className="text-sm text-neutral-700">启用</label>
          </div>
          <div>
            <label className={labelClass} htmlFor="s-bu">基础 URL（用于连通性测试）</label>
            <input id="s-bu" value={addBaseUrl} onChange={(e) => setAddBaseUrl(e.target.value)} className={`mt-1 ${inputClass}`} />
          </div>
          <div>
            <label className={labelClass} htmlFor="s-cat">分类</label>
            <input id="s-cat" value={addCategory} onChange={(e) => setAddCategory(e.target.value)} className={`mt-1 ${inputClass}`} />
          </div>
          <div>
            <label className={labelClass} htmlFor="s-pid">项目</label>
            <select id="s-pid" value={addProjectId ?? ""} onChange={(e) => setAddProjectId(e.target.value === "" ? null : e.target.value)} className={`mt-1 ${selectClass}`}>
              <option value="">全局（无项目）</option>
              {projectOptions.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          {addError ? <p role="alert" className="text-sm text-red-600">{addError}</p> : null}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={closeAdd} className={btnSecondaryClass}>取消</button>
            <button type="submit" disabled={createMutation.isPending} className={btnPrimaryClass}>
              {createMutation.isPending ? "保存中…" : "创建"}
            </button>
          </div>
        </form>
      </Modal>

    </div>
  );
}
