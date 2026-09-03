import { useEffect, useState } from "react";
import { FileText, Search } from "lucide-react";
import { api, errDetail } from "../lib/api";
import { Badge, Button, Card, EmptyState, Input, PageHeader, Select, Spinner, useToast } from "../components/ui";
import type { QuestionnaireOverviewItem } from "../types";

const pageSize = 15;

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  completed: { label: "已完成", cls: "bg-emerald-50 text-emerald-600" },
  sent:      { label: "待完成", cls: "bg-purple-50 text-purple-600" },
};
const qStatus = (s: string) => STATUS_BADGE[s] ?? { label: s, cls: "bg-slate-100 text-slate-500" };

export default function Questionnaires() {
  const { toast } = useToast();
  const [items, setItems] = useState<QuestionnaireOverviewItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [status, setStatus] = useState("");
  const [kw, setKw] = useState("");
  const [searchText, setSearchText] = useState("");

  const load = (p: number, st: string, keyword: string) => {
    setLoading(true);
    api.questionnaires.list({
      page: p,
      page_size: pageSize,
      status: st || undefined,
      search: keyword || undefined,
    })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total); setPage(p); })
      .catch((e) => toast(errDetail(e), "err"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(1, "", ""); /* eslint-disable-next-line */ }, []);

  const doSearch = () => { setKw(searchText.trim()); setPage(1); load(1, status, searchText.trim()); };
  const changeStatus = (v: string) => { setStatus(v); setPage(1); load(1, v, kw); };
  const prev = () => load(page - 1, status, kw);
  const next = () => load(page + 1, status, kw);

  const hasFilter = status !== "" || kw !== "";
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <>
      <PageHeader
        title="问卷管理"
        desc="全部候选人的问卷发送与答题情况（右上角筛选 / 搜索）"
        actions={
          <div className="flex gap-2">
            <div className="relative w-72">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                placeholder="搜索姓名 / 手机…"
                className="!pl-8"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
              />
            </div>
            <div className="w-40 shrink-0">
              <Select value={status} onChange={(e) => changeStatus(e.target.value)}>
                <option value="">全部状态</option>
                <option value="sent">待完成</option>
                <option value="completed">已完成</option>
              </Select>
            </div>
          </div>
        }
      />

      {loading && items.length === 0 ? (
        <Spinner />
      ) : total === 0 ? (
        <EmptyState
          icon={<FileText size={36} />}
          text={hasFilter ? "没有符合条件的问卷记录" : "还没有向候选人发送过问卷"}
        />
      ) : (
        <>
          <Card>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                  <th className="px-5 py-3 font-medium">候选人</th>
                  <th className="px-5 py-3 font-medium">应聘岗位</th>
                  <th className="px-5 py-3 font-medium">问卷</th>
                  <th className="px-5 py-3 font-medium">状态</th>
                  <th className="px-5 py-3 font-medium">答题情况</th>
                  <th className="px-5 py-3 font-medium">发送时间</th>
                  <th className="px-5 py-3 font-medium">完成时间</th>
                </tr>
              </thead>
              <tbody>
                {items.map((q) => {
                  const st = qStatus(q.status);
                  return (
                    <tr key={q.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/70 transition-colors">
                      <td className="px-5 py-3.5">
                        <p className="font-medium text-slate-800">{q.candidate_name || "—"}</p>
                        {q.candidate_phone && <p className="text-xs text-slate-400 tabular-nums">{q.candidate_phone}</p>}
                      </td>
                      <td className="px-5 py-3.5 text-slate-600">{q.position || "—"}</td>
                      <td className="px-5 py-3.5 text-slate-700">{q.title}</td>
                      <td className="px-5 py-3.5"><Badge label={st.label} cls={st.cls} /></td>
                      <td className="px-5 py-3.5">
                        {q.status === "completed" ? (
                          <span className="text-xs text-emerald-600">
                            已完成
                            {q.completed_at && <span className="text-slate-400"> · {new Date(q.completed_at).toLocaleDateString()}</span>}
                          </span>
                        ) : (
                          <span className="text-xs text-slate-400">待填写（暂无作答数据）</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 tabular-nums whitespace-nowrap">
                        {q.sent_at ? new Date(q.sent_at).toLocaleString() : "—"}
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 tabular-nums whitespace-nowrap">
                        {q.completed_at ? new Date(q.completed_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>

          <div className="flex items-center justify-between mt-4">
            <p className="text-xs text-slate-400">共 {total} 条 · 第 {page} / {totalPages} 页</p>
            <div className="flex gap-2">
              <Button variant="outline" disabled={page <= 1} onClick={prev}>上一页</Button>
              <Button variant="outline" disabled={page >= totalPages} onClick={next}>下一页</Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
