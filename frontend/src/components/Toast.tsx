import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, Loader2, X } from 'lucide-react'

export type ToastType = 'loading' | 'success' | 'error'

export interface ToastMessage {
  id: string
  type: ToastType
  title: string
  message?: string
}

let addToastFn: ((t: ToastMessage) => void) | null = null

export function showToast(type: ToastType, title: string, message?: string) {
  if (addToastFn) {
    addToastFn({ id: Date.now().toString(), type, title, message })
  }
}

function getToastStyle(type: ToastType) {
  if (type === 'loading') return 'bg-white/90 border-indigo-200 shadow-indigo-500/10'
  if (type === 'success') return 'bg-emerald-50/90 border-emerald-200'
  return 'bg-red-50/90 border-red-200'
}

function getTitleStyle(type: ToastType) {
  if (type === 'success') return 'text-emerald-800'
  if (type === 'error') return 'text-red-800'
  return 'text-gray-800'
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  useEffect(() => {
    addToastFn = (t: ToastMessage) => {
      setToasts(prev => [...prev, t])
      if (t.type === 'success') {
        setTimeout(() => {
          setToasts(prev => prev.filter(x => x.id !== t.id))
        }, 4000)
      }
    }
    return () => { addToastFn = null }
  }, [])

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`rounded-2xl shadow-xl border p-4 transition-all duration-300 animate-slide-in backdrop-blur-xl ${getToastStyle(toast.type)}`}
        >
          <div className="flex items-start gap-3">
            {toast.type === 'loading' && (
              <div className="w-8 h-8 rounded-xl bg-indigo-100 flex items-center justify-center flex-shrink-0">
                <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
              </div>
            )}
            {toast.type === 'success' && (
              <div className="w-8 h-8 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0">
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              </div>
            )}
            {toast.type === 'error' && (
              <div className="w-8 h-8 rounded-xl bg-red-100 flex items-center justify-center flex-shrink-0">
                <XCircle className="w-4 h-4 text-red-500" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-semibold ${getTitleStyle(toast.type)}`}>{toast.title}</p>
              {toast.type === 'loading' && (
                <div className="mt-2 flex items-center gap-1.5">
                  <div className="h-1.5 flex-1 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-indigo-400 to-purple-500 rounded-full animate-progress-bar" />
                  </div>
                  <span className="text-xs text-gray-400">处理中</span>
                </div>
              )}
              {toast.message && toast.type !== 'loading' && (
                <p className="text-xs text-gray-500 mt-1">{toast.message}</p>
              )}
            </div>
            {toast.type !== 'loading' && (
              <button onClick={() => removeToast(toast.id)} className="p-1 rounded-lg hover:bg-black/5 flex-shrink-0 transition-colors">
                <X className="w-3.5 h-3.5 text-gray-400" />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
