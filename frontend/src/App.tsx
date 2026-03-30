import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getPlatforms } from '@/lib/app-data'
import Dashboard from '@/pages/Dashboard'
import Accounts from '@/pages/Accounts'
import Register from '@/pages/Register'
import Proxies from '@/pages/Proxies'
import Settings from '@/pages/Settings'
import TaskHistory from '@/pages/TaskHistory'
import {
  ChevronDown,
  ChevronRight,
  Globe,
  History,
  LayoutDashboard,
  Moon,
  Settings as SettingsIcon,
  Sun,
  Users,
} from 'lucide-react'

type NavItem = {
  path: string
  label: string
  icon: any
  exact?: boolean
}

const PRIMARY_NAV: NavItem[] = [
  { path: '/', label: '总览', icon: LayoutDashboard, exact: true },
]

const SECONDARY_NAV: NavItem[] = [
  { path: '/history', label: '任务记录', icon: History },
  { path: '/proxies', label: '代理资源', icon: Globe },
  { path: '/settings', label: '配置中心', icon: SettingsIcon },
]

function appNavClass(isActive: boolean) {
  return [
    'group flex items-center gap-2.5 rounded-[16px] px-3 py-2 text-sm transition-all duration-150',
    isActive
      ? 'border border-[var(--accent-edge)] bg-[var(--bg-active)] text-[var(--text-primary)] shadow-[0_18px_34px_rgba(7,15,18,0.34)]'
      : 'border border-transparent text-[var(--text-secondary)] hover:border-[var(--border-soft)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
  ].join(' ')
}

function PlatformGroup({
  groupKey,
  parentLabel,
  children,
  isGroupActive,
}: {
  groupKey: string
  parentLabel: string
  children: { key: string; label: string; group: string }[]
  isGroupActive: boolean
}) {
  const [open, setOpen] = useState(isGroupActive)

  useEffect(() => {
    if (isGroupActive) setOpen(true)
  }, [isGroupActive])

  // 如果父平台也存在于 children 中（同名），从 children 里提取
  const parentInList = children.find(c => c.key === groupKey)
  const childItems = children.filter(c => c.key !== groupKey)

  return (
    <div className="space-y-1">
      {parentInList ? (
        <NavLink
          to={`/accounts/${parentInList.key}`}
          className={({ isActive }) => [
            'flex items-center gap-2 rounded-2xl px-3 py-2 text-sm transition-colors',
            isActive
              ? 'bg-[linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.01))] text-[var(--text-primary)]'
              : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
          ].join(' ')}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]/80" />
          <span className="flex-1">{parentInList.label}</span>
          {childItems.length > 0 && (
            <button
              type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(v => !v) }}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </button>
          )}
        </NavLink>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          className="flex w-full items-center gap-2 rounded-2xl px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]/80" />
          <span className="flex-1 text-left">{parentLabel}</span>
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
      )}
      {open && childItems.length > 0 && (
        <div className="ml-4 space-y-1 border-l border-[var(--border-soft)] pl-3">
          {childItems.map(child => (
            <NavLink
              key={child.key}
              to={`/accounts/${child.key}`}
              className={({ isActive }) => [
                'flex items-center gap-2 rounded-xl px-3 py-1.5 text-[13px] transition-colors',
                isActive
                  ? 'bg-[linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.01))] text-[var(--text-primary)]'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
              ].join(' ')}
            >
              <span className="h-1 w-1 rounded-full bg-[var(--accent)]/60" />
              <span>{child.label}</span>
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

function AccountsSubNav() {
  const location = useLocation()
  const isAccounts = location.pathname.startsWith('/accounts')
  const [open, setOpen] = useState(isAccounts)
  const [platforms, setPlatforms] = useState<{ key: string; label: string }[]>([])

  useEffect(() => {
    if (isAccounts) setOpen(true)
  }, [isAccounts])

  useEffect(() => {
    getPlatforms()
      .then((data) => setPlatforms((data || []).map((p: any) => ({ key: p.name, label: p.display_name, group: p.group || '' }))))
      .catch(() => setPlatforms([]))
  }, [])

  // 计算分组结构：有 group 的归入父组，没有的单独显示
  // 如果某个平台被引用为 group 父节点，也从 standalone 移出
  const groupedPlatforms = (() => {
    const groups: Record<string, { key: string; label: string; group: string }[]> = {}
    const standaloneSet = new Map<string, { key: string; label: string; group: string }>()
    platforms.forEach(p => standaloneSet.set(p.key, p))
    // 先收集所有 group 子项
    platforms.forEach(p => {
      if (p.group) {
        if (!groups[p.group]) groups[p.group] = []
        groups[p.group].push(p)
      }
    })
    // 把被引用为 group 父节点的平台从 standalone 移到 groups 里
    Object.keys(groups).forEach(groupKey => {
      if (standaloneSet.has(groupKey) && !groups[groupKey].some(c => c.key === groupKey)) {
        // 父平台在 standalone 里但不在子项里，把它加进去作为第一个
        const parent = standaloneSet.get(groupKey)!
        groups[groupKey].unshift(parent)
      }
      // 从 standalone 移除所有属于这个 group 的平台
      groups[groupKey].forEach(c => standaloneSet.delete(c.key))
    })
    return { groups, standalone: Array.from(standaloneSet.values()) }
  })()

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`${appNavClass(isAccounts)} w-full justify-between text-left`}
      >
        <span className="flex items-center gap-3">
          <Users className={`h-4 w-4 ${isAccounts ? 'text-[var(--accent)]' : 'text-[var(--text-muted)] group-hover:text-[var(--accent)]'}`} />
          <span>账号资产</span>
        </span>
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>
      {open && (
        <div className="ml-4 space-y-1.5 border-l border-[var(--border-soft)] pl-4">
          {groupedPlatforms.standalone.map((platform) => (
            <NavLink
              key={platform.key}
              to={`/accounts/${platform.key}`}
              className={({ isActive }) => [
                'flex items-center gap-2 rounded-2xl px-3 py-2 text-sm transition-colors',
                isActive
                  ? 'bg-[linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.01))] text-[var(--text-primary)]'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
              ].join(' ')}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]/80" />
              <span>{platform.label}</span>
            </NavLink>
          ))}
          {Object.entries(groupedPlatforms.groups).map(([groupKey, children]) => {
            const parentPlatform = children.find(c => c.key === groupKey)
            const parentLabel = parentPlatform?.label || (groupKey.charAt(0).toUpperCase() + groupKey.slice(1))
            const isGroupActive = children.some(c => location.pathname === `/accounts/${c.key}`)
            return (
              <PlatformGroup
                key={groupKey}
                groupKey={groupKey}
                parentLabel={parentLabel}
                children={children}
                isGroupActive={isGroupActive}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function Sidebar({ theme, toggleTheme }: { theme: string; toggleTheme: () => void }) {
  const isLight = theme === 'light'

  return (
    <aside className="app-sidebar flex w-[15rem] shrink-0 flex-col">
      <div className="flex-1 rounded-[24px] border border-[var(--border)] bg-[linear-gradient(180deg,rgba(255,255,255,0.045),rgba(255,255,255,0.012))] p-3 shadow-[var(--shadow-hard)] backdrop-blur-xl">
        <div className="mb-3 flex items-center justify-between gap-3 rounded-[18px] border border-[var(--border-soft)] bg-[var(--hero-bg)] px-3 py-2.5">
          <div className="text-sm font-semibold text-[var(--text-primary)]">控制台</div>
          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex h-9 w-9 items-center justify-center rounded-[14px] border border-[var(--border-soft)] bg-[var(--chip-bg)] text-[var(--text-secondary)] transition-colors hover:border-[var(--accent)] hover:text-[var(--text-primary)]"
          >
            {isLight ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </button>
        </div>

        <div className="space-y-4">
          <section>
            <div className="mb-2 px-2 text-[11px] uppercase tracking-[0.22em] text-[var(--text-muted)]">入口</div>
            <nav className="space-y-1.5">
              {PRIMARY_NAV.map(({ path, label, icon: Icon, exact }) => (
                <NavLink key={path} to={path} end={exact} className={({ isActive }) => appNavClass(isActive)}>
                  {({ isActive }) => (
                    <>
                      <Icon className={`h-4 w-4 ${isActive ? 'text-[var(--accent)]' : 'text-[var(--text-muted)] group-hover:text-[var(--accent)]'}`} />
                      <span>{label}</span>
                    </>
                  )}
                </NavLink>
              ))}
            </nav>
          </section>

          <section>
            <div className="mb-2 px-2 text-[11px] uppercase tracking-[0.22em] text-[var(--text-muted)]">资产</div>
            <AccountsSubNav />
          </section>

          <section>
            <div className="mb-2 px-2 text-[11px] uppercase tracking-[0.22em] text-[var(--text-muted)]">系统</div>
            <nav className="space-y-1.5">
              {SECONDARY_NAV.map(({ path, label, icon: Icon }) => (
                <NavLink key={path} to={path} className={({ isActive }) => appNavClass(isActive)}>
                  {({ isActive }) => (
                    <>
                      <Icon className={`h-4 w-4 ${isActive ? 'text-[var(--accent)]' : 'text-[var(--text-muted)] group-hover:text-[var(--accent)]'}`} />
                      <span>{label}</span>
                    </>
                  )}
                </NavLink>
              ))}
            </nav>
          </section>
        </div>
      </div>
    </aside>
  )
}

function Shell({ theme, toggleTheme }: { theme: string; toggleTheme: () => void }) {
  return (
    <div className="app-shell min-h-screen p-2.5 lg:p-3">
      <div className="app-window flex min-h-[calc(100vh-1.5rem)] gap-3 p-2.5 lg:p-3">
        <Sidebar theme={theme} toggleTheme={toggleTheme} />
        <div className="flex min-w-0 flex-1 flex-col">
          <main className="min-h-0 flex-1 rounded-[22px] border border-[var(--border)] bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.012))] p-3 shadow-[var(--shadow-hard)] backdrop-blur-xl lg:p-3.5">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/accounts/:platform" element={<Accounts />} />
              <Route path="/register" element={<Register />} />
              <Route path="/history" element={<TaskHistory />} />
              <Route path="/proxies" element={<Proxies />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))

  return (
    <BrowserRouter>
      <Shell theme={theme} toggleTheme={toggleTheme} />
    </BrowserRouter>
  )
}
