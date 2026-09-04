import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, AlertCircle, Loader2, X } from "lucide-react";

// ================= Toast =================
type Toast = { id: number; kind: "ok" | "err"; msg: string };
const ToastCtx = createContext<{ toast: (msg: string, kind?: "ok" | "err") => void }>(null!);
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const toast = useCallback((msg: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((a) => [...a, { id, kind, msg }]);
    setTimeout(() => setItems((a) => a.filter((t) => t.id !== id)), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      <div className="fixed top-4 right-4 z-[100] space-y-2 w-80">
        {items.map((t) => (
          <div
            key={t.id}
            className={`flex items-start gap-2 rounded-xl px-4 py-3 backdrop-blur-xl border shadow-pop text-sm animate-[toastIn_.35s_cubic-bezier(.22,.8,.3,1)] ${
              t.kind === "ok"
                ? "bg-slate-900/85 border-white/10 text-white"
                : "bg-rose-600/90 border-rose-400/30 text-white"
            }`}
          >
            {t.kind === "ok" ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-cyan-300" /> : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
            <span className="flex-1 break-all">{t.msg}</span>
            <button onClick={() => setItems((a) => a.filter((x) => x.id !== t.id))} className="opacity-60 hover:opacity-100 transition-opacity">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ================= 基础组件 =================
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "outline" | "ghost" | "danger";
  loading?: boolean;
};
export function Button({ variant = "primary", loading, className = "", children, disabled, ...rest }: BtnProps) {
  const styles = {
    primary:
      "grad-anim text-white shadow-glow-brand btn-shine hover:shadow-glow-lg hover:-translate-y-[1px] active:translate-y-0",
    outline:
      "border border-slate-200/90 bg-white/70 backdrop-blur text-slate-600 hover:bg-white hover:border-brand-300 hover:text-brand-600 hover:shadow-sm",
    ghost: "text-slate-500 hover:bg-slate-900/5 hover:text-slate-800",
    danger:
      "bg-gradient-to-r from-rose-500 to-rose-600 text-white shadow-[0_8px_24px_rgba(244,63,94,.3)] btn-shine hover:-translate-y-[1px] active:translate-y-0",
  }[variant];
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition-all duration-200 ease-fluid disabled:opacity-50 disabled:pointer-events-none disabled:!translate-y-0 ${styles} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ className = "", style, children }: { className?: string; style?: React.CSSProperties; children: ReactNode }) {
  return (
    <div
      style={style}
      className={`rounded-2xl border border-white/70 bg-white/65 backdrop-blur-xl shadow-glass transition-shadow duration-300 ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeader({ title, desc, actions }: { title: string; desc?: string; actions?: ReactNode }) {
  return (
    <div className="mb-7">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold font-display tracking-tight text-slate-900">{title}</h1>
          {desc && <p className="text-sm text-slate-400 mt-1">{desc}</p>}
        </div>
        {actions && <div className="flex gap-2">{actions}</div>}
      </div>
      <div className="mt-3 h-[3px] w-16 rounded-full grad-anim grow-x" />
    </div>
  );
}

export function Badge({ label, cls }: { label: string; cls?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls ?? "bg-slate-100 text-slate-600"}`}>
      {label}
    </span>
  );
}

export function Spinner({ text = "加载中…" }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <span className="fluid-spinner" />
      <p className="text-sm text-slate-400">{text}</p>
    </div>
  );
}

export function EmptyState({ icon, text }: { icon?: ReactNode; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-slate-300 gap-2">
      {icon ?? <span className="text-4xl">📭</span>}
      <p className="text-sm">{text}</p>
    </div>
  );
}

export function Modal({ open, onClose, title, width = "max-w-lg", children }: {
  open: boolean; onClose: () => void; title: string; width?: string; children: ReactNode;
}) {
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-[90] overflow-y-auto">
      <div className="fixed inset-0 bg-slate-900/10 backdrop-blur-md animate-[fadeIn_.2s_ease-out]" onClick={onClose} />
      <div className="min-h-full flex items-center justify-center p-4">
      <div className={`relative bg-white/90 backdrop-blur-2xl border border-white/80 rounded-2xl shadow-pop w-full ${width} max-h-[calc(100vh-2rem)] overflow-y-auto my-auto animate-[modalIn_.3s_cubic-bezier(.22,.8,.3,1)]`}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 sticky top-0 bg-white/85 backdrop-blur-xl rounded-t-2xl z-10">
          <h3 className="font-semibold font-display text-slate-900">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors"><X size={18} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
      </div>
    </div>,
    document.body
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block mb-4 last:mb-0">
      <span className="block text-xs font-medium text-slate-500 mb-1.5">{label}</span>
      {children}
    </label>
  );
}

const inputCls =
  "w-full rounded-xl border border-slate-200/90 bg-white/70 backdrop-blur px-3 py-2 text-sm outline-none transition-all duration-200 focus:border-brand-400 focus:ring-4 focus:ring-brand-500/15 focus:bg-white placeholder:text-slate-300 hover:border-slate-300";

export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input {...p} className={`${inputCls} ${p.className ?? ""}`} />
);
export const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...p} className={`${inputCls} ${p.className ?? ""}`} />
);
export const Textarea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...p} className={`${inputCls} ${p.className ?? ""}`} />
);

export function Drawer({ open, onClose, title, width = "max-w-md", children }: {
  open: boolean; onClose: () => void; title: string; width?: string; children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-[90] flex justify-end">
      <div className="absolute inset-0 bg-slate-900/10 backdrop-blur-md animate-[fadeIn_.2s_ease-out]" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        className={`relative flex h-full w-full flex-col bg-white/90 backdrop-blur-2xl border-l border-white/80 shadow-pop ${width} animate-[drawerIn_.32s_cubic-bezier(.22,.8,.3,1)]`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 sticky top-0 bg-white/85 backdrop-blur-xl z-10">
          <h3 className="font-semibold font-display text-slate-900 truncate">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors shrink-0 ml-3">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-5">{children}</div>
      </aside>
    </div>,
    document.body
  );
}
