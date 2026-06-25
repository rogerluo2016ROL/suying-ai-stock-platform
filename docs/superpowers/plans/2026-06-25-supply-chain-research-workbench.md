# Supply Chain Research Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“大葱产业链拆解”页面改造为三栏投研工作台，支持节点下钻、候选对比、证据查看和映射复核。

**Architecture:** 保留现有 `SupplyChainBom.tsx` 作为页面入口，把主要体验下沉到新的 `SupplyChainResearchWorkbench.tsx` 容器。容器管理选中节点、选中公司、对比列表和复核刷新；左栏、中栏、右栏拆成独立组件。复用现有 screener API，不新增后端迁移。

**Tech Stack:** React 18 + TypeScript 5.6 + Vite 6 + Ant Design 5.22 + Vitest + Testing Library.

## Global Constraints

- 本阶段只改前端工作台体验，复用已完成的后端能力。
- 不新增数据库迁移，不新增交易相关能力，不改变模型评分算法。
- 若需要补后端字段，只允许做兼容式字段扩展。
- 工作台是工具界面，不做营销式 hero。
- 表格保持高密度、低装饰、便于扫描。
- 核心表格统一 `scroll.x`，单元格默认不换行。
- 卡片只用于明确的工具面板，不做卡片套卡片。
- 重要状态用 Ant Design `Tag`，操作按钮带图标。
- 宽屏下三栏并排；窄屏下降级为上下顺序：节点、候选、证据。
- 节点候选为空时显示“该节点缺少公司映射证据”，不回退全局候选。

---

## File Structure

Create:

- `frontend/src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx`  
  三栏工作台容器，维护选中节点、选中公司、对比列表和刷新协调。
- `frontend/src/pages/supply-chain-bom/SupplyChainNodeNavigator.tsx`  
  左栏节点树、hotspot、节点摘要。
- `frontend/src/pages/supply-chain-bom/SupplyChainCandidateGrid.tsx`  
  中栏候选表、状态筛选、多选。
- `frontend/src/pages/supply-chain-bom/CandidateCompareBar.tsx`  
  候选公司横向对比栏。
- `frontend/src/pages/supply-chain-bom/CompanyEvidencePanel.tsx`  
  右栏证据链、财务、研报和复核动作。
- `frontend/src/__tests__/SupplyChainResearchWorkbench.test.tsx`
- `frontend/src/__tests__/SupplyChainNodeNavigator.test.tsx`
- `frontend/src/__tests__/SupplyChainCandidateGrid.test.tsx`
- `frontend/src/__tests__/CompanyEvidencePanel.test.tsx`

Modify:

- `frontend/src/pages/SupplyChainBom.tsx`  
  用 `SupplyChainResearchWorkbench` 替换当前大量纵向区块的主要投研工作流，保留政策解读等非本阶段核心区块时要放到工作台后方。
- `frontend/src/pages/supply-chain-bom/types.ts`  
  补充工作台需要的映射字段、证据字段和对比字段类型。
- `frontend/src/api/client.ts`  
  仅在缺少类型时补充兼容字段；已有复核 API 方法应复用。

---

### Task 1: Extend Frontend Types For Workbench Data

**Files:**
- Modify: `frontend/src/pages/supply-chain-bom/types.ts`
- Test: `frontend/src/__tests__/SupplyChainCandidateGrid.test.tsx`

**Interfaces:**
- Consumes: existing `CandidateCompany`, `BomNode`, `SelectedNodeThesis`.
- Produces:
  - `CandidateCompany.mapping_status?: string`
  - `CandidateCompany.mapping_source?: string`
  - `CandidateCompany.mapping_confidence?: number`
  - `CandidateCompany.mapping_quality_weight?: number`
  - `CandidateCompany.mapping_adjusted_score?: number`
  - `CandidateCompany.node_id?: string`
  - `CandidateCompany.node_name?: string`
  - `CandidateCompany.report_titles?: string[]`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/SupplyChainCandidateGrid.test.tsx` with:

```tsx
import { render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainCandidateGrid from '../pages/supply-chain-bom/SupplyChainCandidateGrid'
import type { CandidateCompany } from '../pages/supply-chain-bom/types'

const candidates: CandidateCompany[] = [{
  code: '300308',
  name: '中际旭创',
  industry: '通信设备',
  chain: 'AI算力',
  layer: '硬件',
  score: 72.4,
  mapping_adjusted_score: 72.4,
  mapping_status: 'verified',
  mapping_source: 'main_business',
  mapping_confidence: 0.85,
  evidence_gaps: [],
}]

it('renders mapping-adjusted score and mapping status without wrapping core cells', () => {
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainCandidateGrid
        candidates={candidates}
        selectedCodes={[]}
        onToggleCompare={() => {}}
        onOpenCompany={() => {}}
      />
    </ConfigProvider>,
  )

  expect(screen.getByText('中际旭创')).toBeInTheDocument()
  expect(screen.getByText('72.4')).toBeInTheDocument()
  expect(screen.getByText('已确认')).toBeInTheDocument()
  expect(screen.getByTestId('candidate-grid-wrap')).toHaveStyle({ whiteSpace: 'nowrap' })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainCandidateGrid.test.tsx
```

Expected: FAIL because `SupplyChainCandidateGrid` does not exist.

- [ ] **Step 3: Extend types**

Update `CandidateCompany` in `frontend/src/pages/supply-chain-bom/types.ts`:

```ts
  node_id?: string
  node_name?: string
  mapping_confidence?: number
  mapping_status?: string
  mapping_source?: string
  mapping_quality_weight?: number
  mapping_adjusted_score?: number
  report_titles?: string[]
```

- [ ] **Step 4: Keep the test red**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainCandidateGrid.test.tsx
```

Expected: still FAIL because the component is not implemented; type errors should be gone.

---

### Task 2: Build Candidate Grid And Compare Bar

**Files:**
- Create: `frontend/src/pages/supply-chain-bom/SupplyChainCandidateGrid.tsx`
- Create: `frontend/src/pages/supply-chain-bom/CandidateCompareBar.tsx`
- Modify: `frontend/src/__tests__/SupplyChainCandidateGrid.test.tsx`

**Interfaces:**
- Consumes:
  - `CandidateCompany[]`
  - `selectedCodes: string[]`
  - `onToggleCompare(company: CandidateCompany): void`
  - `onOpenCompany(company: CandidateCompany): void`
- Produces:
  - table row click opens company
  - checkbox toggles compare selection
  - status filter limits rows
  - `CandidateCompareBar` renders selected candidates.

- [ ] **Step 1: Add comparison test**

Append to `SupplyChainCandidateGrid.test.tsx`:

```tsx
it('supports selecting candidates for comparison', () => {
  const onToggleCompare = vi.fn()
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainCandidateGrid
        candidates={candidates}
        selectedCodes={[]}
        onToggleCompare={onToggleCompare}
        onOpenCompany={() => {}}
      />
    </ConfigProvider>,
  )

  screen.getByRole('checkbox', { name: /对比 中际旭创/ }).click()

  expect(onToggleCompare).toHaveBeenCalledWith(candidates[0])
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainCandidateGrid.test.tsx
```

Expected: FAIL because `SupplyChainCandidateGrid` is missing.

- [ ] **Step 3: Implement `CandidateCompareBar.tsx`**

Create `frontend/src/pages/supply-chain-bom/CandidateCompareBar.tsx`:

```tsx
import { Empty, Space, Table, Tag, Typography } from 'antd'
import type { CandidateCompany } from './types'
import { formatNumber } from './formatters'

const { Text } = Typography

interface CandidateCompareBarProps {
  candidates: CandidateCompany[]
}

export default function CandidateCompareBar({ candidates }: CandidateCompareBarProps) {
  if (!candidates.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="勾选候选公司后进行横向对比" />
  }

  const columns: any[] = [
    { title: '公司', dataIndex: 'name', width: 140, render: (_: string, row: CandidateCompany) => <Text strong>{row.name || row.code}</Text> },
    { title: '收入增速', dataIndex: ['financial_indicators', 'revenue_growth'], width: 110, render: (v: number) => `${formatNumber(v, 1)}%` },
    { title: '利润增速', dataIndex: ['financial_indicators', 'profit_growth'], width: 110, render: (v: number) => `${formatNumber(v, 1)}%` },
    { title: 'ROE', dataIndex: ['financial_indicators', 'roe'], width: 90, render: (v: number) => `${formatNumber(v, 1)}%` },
    { title: '映射可信', dataIndex: 'mapping_confidence', width: 100, render: (v: number) => formatNumber(v, 2) },
    { title: '证据来源', dataIndex: 'mapping_source', width: 120 },
    { title: '缺口', dataIndex: 'evidence_gaps', width: 160, render: (gaps: string[] = []) => <Tag color={gaps.length ? 'orange' : 'green'}>{gaps.length}</Tag> },
  ]

  return (
    <Table
      rowKey="code"
      size="small"
      columns={columns}
      dataSource={candidates}
      pagination={false}
      scroll={{ x: 830 }}
    />
  )
}
```

- [ ] **Step 4: Implement `SupplyChainCandidateGrid.tsx`**

Create `frontend/src/pages/supply-chain-bom/SupplyChainCandidateGrid.tsx`:

```tsx
import { Button, Checkbox, Empty, Select, Space, Table, Tag, Typography } from 'antd'
import { EyeOutlined } from '@ant-design/icons'
import { useMemo, useState } from 'react'
import type { CandidateCompany } from './types'
import { formatNumber, scoreColor } from './formatters'
import CandidateCompareBar from './CandidateCompareBar'

const { Text } = Typography

function statusText(status?: string) {
  if (status === 'verified') return '已确认'
  if (status === 'pending_review') return '待复核'
  if (status === 'weak_evidence') return '弱证据'
  if (status === 'rejected') return '已驳回'
  return status || '待复核'
}

function statusColor(status?: string) {
  if (status === 'verified') return 'green'
  if (status === 'pending_review') return 'gold'
  if (status === 'weak_evidence') return 'orange'
  if (status === 'rejected') return 'red'
  return 'default'
}

interface SupplyChainCandidateGridProps {
  candidates: CandidateCompany[]
  loading?: boolean
  selectedCodes: string[]
  selectedNodeName?: string
  mappingMessage?: string
  onToggleCompare: (company: CandidateCompany) => void
  onOpenCompany: (company: CandidateCompany) => void
}

export default function SupplyChainCandidateGrid({
  candidates,
  loading = false,
  selectedCodes,
  selectedNodeName,
  mappingMessage,
  onToggleCompare,
  onOpenCompany,
}: SupplyChainCandidateGridProps) {
  const [statusFilter, setStatusFilter] = useState('all')
  const filtered = useMemo(
    () => statusFilter === 'all' ? candidates : candidates.filter(item => item.mapping_status === statusFilter),
    [candidates, statusFilter],
  )
  const selectedCandidates = candidates.filter(item => selectedCodes.includes(item.code))

  const columns: any[] = [
    {
      title: '',
      width: 54,
      fixed: 'left',
      render: (_: unknown, row: CandidateCompany) => (
        <Checkbox
          aria-label={`对比 ${row.name || row.code}`}
          checked={selectedCodes.includes(row.code)}
          onChange={() => onToggleCompare(row)}
        />
      ),
    },
    {
      title: '公司',
      width: 150,
      fixed: 'left',
      render: (_: unknown, row: CandidateCompany) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => onOpenCompany(row)}>
          {row.name || row.code}
        </Button>
      ),
    },
    { title: '行业', dataIndex: 'industry', width: 120 },
    { title: '链路节点', width: 180, render: (_: unknown, row: CandidateCompany) => `${row.chain || row.bom_path?.[0] || '--'} / ${row.node_name || row.layer || '--'}` },
    { title: '原始分', width: 90, render: (_: unknown, row: CandidateCompany) => <Tag color={scoreColor(row.score)}>{formatNumber(row.score, 1)}</Tag> },
    { title: '调整分', width: 90, render: (_: unknown, row: CandidateCompany) => <Tag color="blue">{formatNumber(row.mapping_adjusted_score ?? row.score, 1)}</Tag> },
    { title: '映射', dataIndex: 'mapping_status', width: 100, render: (value: string) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
    { title: '证据来源', dataIndex: 'mapping_source', width: 120 },
    { title: '信号', dataIndex: 'trade_signal', width: 100 },
    { title: '证据缺口', width: 220, render: (_: unknown, row: CandidateCompany) => <Space wrap={false}>{(row.evidence_gaps || []).slice(0, 2).map(gap => <Tag key={gap}>{gap}</Tag>)}</Space> },
  ]

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space>
          <Text strong>候选对比</Text>
          <Tag color="blue">{filtered.length}</Tag>
        </Space>
        <Select
          value={statusFilter}
          style={{ width: 140 }}
          onChange={setStatusFilter}
          options={[
            { value: 'all', label: '全部' },
            { value: 'verified', label: '已确认' },
            { value: 'pending_review', label: '待复核' },
            { value: 'weak_evidence', label: '弱证据' },
          ]}
        />
      </Space>
      <div data-testid="candidate-grid-wrap" style={{ whiteSpace: 'nowrap' }}>
        <Table
          rowKey="code"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          scroll={{ x: 1234 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={selectedNodeName ? mappingMessage || '该节点缺少公司映射证据' : '暂无候选公司'} /> }}
        />
      </div>
      <CandidateCompareBar candidates={selectedCandidates} />
    </Space>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainCandidateGrid.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/supply-chain-bom/types.ts frontend/src/pages/supply-chain-bom/SupplyChainCandidateGrid.tsx frontend/src/pages/supply-chain-bom/CandidateCompareBar.tsx frontend/src/__tests__/SupplyChainCandidateGrid.test.tsx
git commit -m "feat: add supply chain candidate comparison grid"
```

---

### Task 3: Build Node Navigator

**Files:**
- Create: `frontend/src/pages/supply-chain-bom/SupplyChainNodeNavigator.tsx`
- Create: `frontend/src/__tests__/SupplyChainNodeNavigator.test.tsx`

**Interfaces:**
- Consumes:
  - `themes: ThemeRow[]`
  - `nodes: BomNode[]`
  - `selectedThemeId: string`
  - `selectedNodeId: string`
  - `quality?: SupplyChainMappingQuality`
  - `selectedNodeThesis?: SelectedNodeThesis`
  - `candidateCount: number`
  - `evidenceCount: number`
  - `onSelectTheme(themeId: string): void`
  - `onSelectNode(node: BomNode): void`
- Produces: selected node events and hotspot visibility.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/SupplyChainNodeNavigator.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainNodeNavigator from '../pages/supply-chain-bom/SupplyChainNodeNavigator'

const themes = [{ theme_id: 'future_industry_core', name: '未来产业主攻方向', policy_weight: 1.5, keywords: [], node_count: 1 }]
const nodes = [{
  node_id: 'semiconductor_materials',
  theme_id: 'future_industry_core',
  chain_id: 'semiconductor',
  level: 'layer',
  name: '材料',
  node_type: 'layer',
  keywords: ['光刻胶'],
  policy_theme: '未来产业主攻方向',
}]
const quality = {
  mapping_count: 15642,
  review_queue_count: 14573,
  status_counts: { verified: 1069, pending_review: 10547, weak_evidence: 4026 },
  source_counts: {},
  hotspot_nodes: [{ node_id: 'semiconductor_materials', node_name: '材料', chain_id: 'semiconductor', pending_review: 460, weak_evidence: 82, verified: 38, rejected: 0, review_pressure: 542 }],
}

it('shows hotspot pressure and selects a node', () => {
  const onSelectNode = vi.fn()
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainNodeNavigator
        themes={themes}
        nodes={nodes}
        selectedThemeId="future_industry_core"
        selectedNodeId=""
        quality={quality}
        selectedNodeThesis={{}}
        candidateCount={0}
        evidenceCount={0}
        onSelectTheme={() => {}}
        onSelectNode={onSelectNode}
      />
    </ConfigProvider>,
  )

  expect(screen.getByText('产业链导航')).toBeInTheDocument()
  expect(screen.getByText('待复核压力 542')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /材料/ }))
  expect(onSelectNode).toHaveBeenCalledWith(nodes[0])
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainNodeNavigator.test.tsx
```

Expected: FAIL because `SupplyChainNodeNavigator` does not exist.

- [ ] **Step 3: Implement node navigator**

Create `frontend/src/pages/supply-chain-bom/SupplyChainNodeNavigator.tsx`:

```tsx
import { Button, Empty, Space, Table, Tag, Typography } from 'antd'
import { ApartmentOutlined } from '@ant-design/icons'
import type { SupplyChainMappingQuality } from '../../api/client'
import type { BomNode, SelectedNodeThesis, ThemeRow } from './types'
import NodeThesisPanel from './NodeThesisPanel'

const { Text } = Typography

interface SupplyChainNodeNavigatorProps {
  themes: ThemeRow[]
  nodes: BomNode[]
  selectedThemeId: string
  selectedNodeId: string
  quality?: SupplyChainMappingQuality | null
  selectedNodeThesis: SelectedNodeThesis
  candidateCount: number
  evidenceCount: number
  onSelectTheme: (themeId: string) => void
  onSelectNode: (node: BomNode) => void
}

export default function SupplyChainNodeNavigator({
  themes,
  nodes,
  selectedThemeId,
  selectedNodeId,
  quality,
  selectedNodeThesis,
  candidateCount,
  evidenceCount,
  onSelectTheme,
  onSelectNode,
}: SupplyChainNodeNavigatorProps) {
  const pressureByNode = new Map((quality?.hotspot_nodes || []).map(item => [item.node_id, Number(item.review_pressure || 0)]))
  const filteredNodes = selectedThemeId ? nodes.filter(node => node.theme_id === selectedThemeId) : nodes
  const selectedTheme = themes.find(theme => theme.theme_id === selectedThemeId)
  const selectedNode = nodes.find(node => node.node_id === selectedNodeId)
  const columns: any[] = [
    {
      title: '节点',
      render: (_: unknown, row: BomNode) => (
        <Button type="link" icon={<ApartmentOutlined />} onClick={() => onSelectNode(row)}>
          {row.name}
        </Button>
      ),
    },
    {
      title: '压力',
      width: 120,
      render: (_: unknown, row: BomNode) => {
        const pressure = pressureByNode.get(row.node_id) || 0
        return pressure ? <Tag color="orange">待复核压力 {pressure}</Tag> : <Tag>低</Tag>
      },
    },
  ]

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Text strong>产业链导航</Text>
        <Tag color="gold">待复核 {quality?.review_queue_count || 0}</Tag>
      </Space>
      <Space wrap>
        {themes.map(theme => (
          <Button key={theme.theme_id} size="small" type={theme.theme_id === selectedThemeId ? 'primary' : 'default'} onClick={() => onSelectTheme(theme.theme_id)}>
            {theme.name}
          </Button>
        ))}
      </Space>
      <Table
        rowKey="node_id"
        size="small"
        columns={columns}
        dataSource={filteredNodes}
        pagination={{ pageSize: 8, showSizeChanger: false }}
        rowClassName={row => row.node_id === selectedNodeId ? 'ant-table-row-selected' : ''}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无节点" /> }}
      />
      <NodeThesisPanel
        node={selectedNode}
        thesis={selectedNodeThesis}
        candidateCount={candidateCount}
        evidenceCount={evidenceCount}
        policyWeight={selectedTheme?.policy_weight || 1}
      />
    </Space>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainNodeNavigator.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/supply-chain-bom/SupplyChainNodeNavigator.tsx frontend/src/__tests__/SupplyChainNodeNavigator.test.tsx
git commit -m "feat: add supply chain node navigator"
```

---

### Task 4: Build Company Evidence Panel

**Files:**
- Create: `frontend/src/pages/supply-chain-bom/CompanyEvidencePanel.tsx`
- Create: `frontend/src/__tests__/CompanyEvidencePanel.test.tsx`

**Interfaces:**
- Consumes:
  - `company: CandidateCompany | null`
  - `loading?: boolean`
  - `onReview(code: string, nodeId: string, decision: 'verified' | 'rejected' | 'needs_more_evidence'): Promise<void>`
- Produces:
  - evidence tabs
  - review action calls
  - empty state when no company selected.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/CompanyEvidencePanel.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import CompanyEvidencePanel from '../pages/supply-chain-bom/CompanyEvidencePanel'
import type { CandidateCompany } from '../pages/supply-chain-bom/types'

const company: CandidateCompany = {
  code: '301526',
  name: '国际复材',
  node_id: 'semiconductor_materials',
  node_name: '材料',
  mapping_status: 'pending_review',
  mapping_confidence: 0.8,
  mapping_source: 'introduction',
  products: ['电子级玻璃布'],
  evidence_gaps: ['是否有明确客户或供应链认证'],
  financial_indicators: { revenue_growth: 12.3, profit_growth: 22.4, roe: 11.2, gross_margin: 33.1 },
  moat_evidence: [{ evidence_type: 'moat_signal', summary: '电子级玻璃布' }],
}

it('shows evidence and submits review decision', async () => {
  const onReview = vi.fn().mockResolvedValue(undefined)
  render(
    <ConfigProvider locale={zhCN}>
      <CompanyEvidencePanel company={company} onReview={onReview} />
    </ConfigProvider>,
  )

  expect(screen.getByText('国际复材')).toBeInTheDocument()
  expect(screen.getByText('电子级玻璃布')).toBeInTheDocument()
  expect(screen.getByText('是否有明确客户或供应链认证')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /确认/ }))
  await waitFor(() => {
    expect(onReview).toHaveBeenCalledWith('301526', 'semiconductor_materials', 'verified')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npx vitest run src/__tests__/CompanyEvidencePanel.test.tsx
```

Expected: FAIL because `CompanyEvidencePanel` does not exist.

- [ ] **Step 3: Implement `CompanyEvidencePanel.tsx`**

Create `frontend/src/pages/supply-chain-bom/CompanyEvidencePanel.tsx`:

```tsx
import { Button, Descriptions, Empty, Progress, Space, Tabs, Tag, Typography } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, WarningOutlined } from '@ant-design/icons'
import type { CandidateCompany } from './types'
import { dimensionLabel, formatNumber } from './formatters'

const { Text } = Typography

interface CompanyEvidencePanelProps {
  company: CandidateCompany | null
  loading?: boolean
  onReview: (code: string, nodeId: string, decision: 'verified' | 'rejected' | 'needs_more_evidence') => Promise<void>
}

export default function CompanyEvidencePanel({ company, onReview }: CompanyEvidencePanelProps) {
  if (!company) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择候选公司查看证据" />
  }
  const nodeId = company.node_id || ''
  const financial = company.financial_indicators || {}
  const dimensionEntries = Object.entries(company.dimension_scores || {})
  const canReview = Boolean(company.code && nodeId)

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space direction="vertical" size={2}>
          <Text strong>{company.name || company.code}</Text>
          <Text type="secondary">{company.code}</Text>
        </Space>
        <Tag color={company.mapping_status === 'verified' ? 'green' : 'gold'}>
          {company.mapping_status || 'pending_review'}
        </Tag>
      </Space>
      <Tabs
        items={[
          {
            key: 'evidence',
            label: '证据链',
            children: (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="映射节点">{company.node_name || company.layer || '--'}</Descriptions.Item>
                  <Descriptions.Item label="置信度">{formatNumber(company.mapping_confidence, 2)}</Descriptions.Item>
                  <Descriptions.Item label="来源">{company.mapping_source || '--'}</Descriptions.Item>
                  <Descriptions.Item label="产品">{company.products?.join('、') || '--'}</Descriptions.Item>
                </Descriptions>
                <Space wrap>
                  {(company.moat_evidence || []).map((item, index) => <Tag key={`${item.summary}-${index}`} color="purple">{item.summary || item.evidence_type}</Tag>)}
                  {!(company.moat_evidence || []).length && <Tag>等待专利、客户、产能证据</Tag>}
                </Space>
                <Space wrap>
                  {(company.evidence_gaps || []).map(gap => <Tag key={gap} color="orange">{gap}</Tag>)}
                </Space>
              </Space>
            ),
          },
          {
            key: 'financial',
            label: '财务',
            children: (
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="收入增速">{formatNumber(financial.revenue_growth)}%</Descriptions.Item>
                <Descriptions.Item label="利润增速">{formatNumber(financial.profit_growth)}%</Descriptions.Item>
                <Descriptions.Item label="ROE">{formatNumber(financial.roe)}%</Descriptions.Item>
                <Descriptions.Item label="毛利率">{formatNumber(financial.gross_margin)}%</Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: 'score',
            label: '评分',
            children: (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                {dimensionEntries.map(([key, value]) => (
                  <div key={key}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Text>{dimensionLabel[key] || key}</Text>
                      <Text>{formatNumber(value, 1)}</Text>
                    </Space>
                    <Progress percent={Math.min(100, Number(value) * 5)} showInfo={false} size="small" />
                  </div>
                ))}
                {!dimensionEntries.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评分拆解" />}
              </Space>
            ),
          },
          {
            key: 'review',
            label: '复核',
            children: (
              <Space wrap>
                <Button type="primary" icon={<CheckCircleOutlined />} disabled={!canReview} onClick={() => onReview(company.code, nodeId, 'verified')}>确认</Button>
                <Button icon={<WarningOutlined />} disabled={!canReview} onClick={() => onReview(company.code, nodeId, 'needs_more_evidence')}>补证据</Button>
                <Button danger icon={<CloseCircleOutlined />} disabled={!canReview} onClick={() => onReview(company.code, nodeId, 'rejected')}>驳回</Button>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npx vitest run src/__tests__/CompanyEvidencePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/supply-chain-bom/CompanyEvidencePanel.tsx frontend/src/__tests__/CompanyEvidencePanel.test.tsx
git commit -m "feat: add supply chain evidence panel"
```

---

### Task 5: Compose Three-Column Workbench Container

**Files:**
- Create: `frontend/src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx`
- Create: `frontend/src/__tests__/SupplyChainResearchWorkbench.test.tsx`

**Interfaces:**
- Consumes:
  - `themes`, `nodes`, `model`, `candidates`, `nodeCandidates`, `selectedNodeThesis`, `nodeDetail`, `dataFreshness`, `quality`, `reviewQueue`
  - callbacks for `selectTheme`, `selectNode`, `openCompany`, `reviewMapping`, `refreshQuality`
- Produces:
  - three-column layout
  - compare selection state
  - selected company state.

- [ ] **Step 1: Write failing container test**

Create `frontend/src/__tests__/SupplyChainResearchWorkbench.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainResearchWorkbench from '../pages/supply-chain-bom/SupplyChainResearchWorkbench'

const themes = [{ theme_id: 'future_industry_core', name: '未来产业主攻方向', policy_weight: 1.5, keywords: [], node_count: 1 }]
const nodes = [{ node_id: 'semiconductor_materials', theme_id: 'future_industry_core', chain_id: 'semiconductor', level: 'layer', name: '材料', node_type: 'layer', keywords: ['光刻胶'], policy_theme: '未来产业主攻方向' }]
const candidate = { code: '301526', name: '国际复材', node_id: 'semiconductor_materials', node_name: '材料', chain: '半导体', score: 70, mapping_adjusted_score: 66.5, mapping_status: 'pending_review', mapping_source: 'introduction', products: ['电子级玻璃布'], evidence_gaps: ['是否有明确客户或供应链认证'] }
const quality = { mapping_count: 1, review_queue_count: 1, status_counts: { pending_review: 1 }, source_counts: {}, hotspot_nodes: [{ node_id: 'semiconductor_materials', node_name: '材料', chain_id: 'semiconductor', review_pressure: 1 }] }

it('connects node, candidate, evidence and review workflow in one screen', () => {
  const onSelectNode = vi.fn()
  const onReviewMapping = vi.fn().mockResolvedValue(undefined)
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainResearchWorkbench
        themes={themes}
        nodes={nodes}
        candidates={[candidate]}
        activeCandidates={[candidate]}
        selectedThemeId="future_industry_core"
        selectedNodeId=""
        selectedNodeThesis={{}}
        candidateLoading={false}
        quality={quality as any}
        onSelectTheme={() => {}}
        onSelectNode={onSelectNode}
        onOpenCompany={() => {}}
        onReviewMapping={onReviewMapping}
      />
    </ConfigProvider>,
  )

  expect(screen.getByText('产业链导航')).toBeInTheDocument()
  expect(screen.getByText('候选对比')).toBeInTheDocument()
  expect(screen.getByText('请选择候选公司查看证据')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /国际复材/ }))
  expect(screen.getByText('电子级玻璃布')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainResearchWorkbench.test.tsx
```

Expected: FAIL because `SupplyChainResearchWorkbench` does not exist.

- [ ] **Step 3: Implement workbench container**

Create `frontend/src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx`:

```tsx
import { Col, Row } from 'antd'
import { useMemo, useState } from 'react'
import type { SupplyChainMappingQuality } from '../../api/client'
import type { BomNode, CandidateCompany, SelectedNodeThesis, ThemeRow } from './types'
import CompanyEvidencePanel from './CompanyEvidencePanel'
import SupplyChainCandidateGrid from './SupplyChainCandidateGrid'
import SupplyChainNodeNavigator from './SupplyChainNodeNavigator'

interface SupplyChainResearchWorkbenchProps {
  themes: ThemeRow[]
  nodes: BomNode[]
  candidates: CandidateCompany[]
  activeCandidates: CandidateCompany[]
  selectedThemeId: string
  selectedNodeId: string
  selectedNodeThesis: SelectedNodeThesis
  candidateLoading?: boolean
  quality?: SupplyChainMappingQuality | null
  nodeDetail?: any
  onSelectTheme: (themeId: string) => void
  onSelectNode: (node: BomNode) => void
  onOpenCompany: (company: CandidateCompany) => void
  onReviewMapping: (code: string, nodeId: string, decision: 'verified' | 'rejected' | 'needs_more_evidence') => Promise<void>
}

export default function SupplyChainResearchWorkbench({
  themes,
  nodes,
  activeCandidates,
  selectedThemeId,
  selectedNodeId,
  selectedNodeThesis,
  candidateLoading = false,
  quality,
  nodeDetail,
  onSelectTheme,
  onSelectNode,
  onOpenCompany,
  onReviewMapping,
}: SupplyChainResearchWorkbenchProps) {
  const [selectedCompany, setSelectedCompany] = useState<CandidateCompany | null>(null)
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const selectedNode = useMemo(() => nodes.find(node => node.node_id === selectedNodeId), [nodes, selectedNodeId])

  const toggleCompare = (company: CandidateCompany) => {
    setSelectedCodes(prev => {
      if (prev.includes(company.code)) return prev.filter(code => code !== company.code)
      return [...prev, company.code].slice(0, 4)
    })
  }

  const openCompany = (company: CandidateCompany) => {
    setSelectedCompany(company)
    onOpenCompany(company)
  }

  return (
    <Row gutter={[12, 12]} align="stretch">
      <Col xs={24} xl={6}>
        <div style={{ height: '100%', border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 12 }}>
          <SupplyChainNodeNavigator
            themes={themes}
            nodes={nodes}
            selectedThemeId={selectedThemeId}
            selectedNodeId={selectedNodeId}
            quality={quality}
            selectedNodeThesis={selectedNodeThesis}
            candidateCount={activeCandidates.length}
            evidenceCount={nodeDetail?.evidence?.length || 0}
            onSelectTheme={onSelectTheme}
            onSelectNode={onSelectNode}
          />
        </div>
      </Col>
      <Col xs={24} xl={11}>
        <div style={{ height: '100%', border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 12 }}>
          <SupplyChainCandidateGrid
            candidates={activeCandidates}
            loading={candidateLoading}
            selectedCodes={selectedCodes}
            selectedNodeName={selectedNode?.name}
            mappingMessage={selectedNodeThesis.mapping_message}
            onToggleCompare={toggleCompare}
            onOpenCompany={openCompany}
          />
        </div>
      </Col>
      <Col xs={24} xl={7}>
        <div style={{ height: '100%', border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 12 }}>
          <CompanyEvidencePanel company={selectedCompany} onReview={onReviewMapping} />
        </div>
      </Col>
    </Row>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainResearchWorkbench.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx frontend/src/__tests__/SupplyChainResearchWorkbench.test.tsx
git commit -m "feat: compose supply chain research workbench"
```

---

### Task 6: Integrate Workbench Into SupplyChainBom Page

**Files:**
- Modify: `frontend/src/pages/SupplyChainBom.tsx`
- Modify: `frontend/src/__tests__/SupplyChainBom.test.tsx`

**Interfaces:**
- Consumes components from Tasks 2-5.
- Produces:
  - page-level data loading for quality and review actions
  - `SupplyChainResearchWorkbench` mounted in page.

- [ ] **Step 1: Write failing page integration test**

Add to `frontend/src/__tests__/SupplyChainBom.test.tsx`:

```tsx
it('renders the three-column research workbench', async () => {
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainBom />
    </ConfigProvider>,
  )

  expect(await screen.findByText('产业链导航')).toBeInTheDocument()
  expect(screen.getByText('候选对比')).toBeInTheDocument()
  expect(screen.getByText('请选择候选公司查看证据')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainBom.test.tsx --testNamePattern "three-column research workbench"
```

Expected: FAIL if the page still renders the old vertical workflow.

- [ ] **Step 3: Add page state and API wiring**

In `SupplyChainBom.tsx`, import:

```tsx
import SupplyChainResearchWorkbench from './supply-chain-bom/SupplyChainResearchWorkbench'
import type { SupplyChainMappingQuality } from '../api/client'
```

Add state near existing state declarations:

```tsx
const [mappingQuality, setMappingQuality] = useState<SupplyChainMappingQuality | null>(null)
const [mappingQualityLoading, setMappingQualityLoading] = useState(false)
```

Add loader:

```tsx
const loadMappingQuality = async () => {
  setMappingQualityLoading(true)
  try {
    const resp = await screenerApi.getSupplyChainMappingQuality()
    setMappingQuality(resp.data)
  } catch (err) {
    console.error('Mapping quality load failed:', err)
    message.warning('映射质量报告加载失败')
  } finally {
    setMappingQualityLoading(false)
  }
}
```

Call it in initial `useEffect` after workbench load starts:

```tsx
loadMappingQuality()
```

Add review handler:

```tsx
const reviewMapping = async (
  code: string,
  nodeId: string,
  decision: 'verified' | 'rejected' | 'needs_more_evidence',
) => {
  await screenerApi.reviewSupplyChainMapping(code, nodeId, {
    decision,
    reviewer: 'frontend',
    note: decision === 'verified' ? '前端工作台确认' : decision === 'rejected' ? '前端工作台驳回' : '前端工作台要求补充证据',
  })
  message.success('复核结果已写回')
  await loadMappingQuality()
  if (selectedNodeId) {
    const node = nodes.find(item => item.node_id === selectedNodeId)
    if (node) selectNode(node)
  }
}
```

- [ ] **Step 4: Mount workbench**

Replace the old top-level BOM graph + candidate table block with:

```tsx
<SupplyChainResearchWorkbench
  themes={themes}
  nodes={nodes}
  candidates={candidates}
  activeCandidates={displayCandidates}
  selectedThemeId={selectedThemeId}
  selectedNodeId={selectedNodeId}
  selectedNodeThesis={selectedNodeThesis}
  candidateLoading={candidateLoading || chainCandidateLoading || mappingQualityLoading}
  quality={mappingQuality}
  nodeDetail={nodeDetail}
  onSelectTheme={selectTheme}
  onSelectNode={selectNode}
  onOpenCompany={openCompany}
  onReviewMapping={reviewMapping}
/>
```

Keep `CandidateFilterBar`, `ChainBubbleChart`, `SupplyChainMappingReviewPanel`, upstream observation pool, and policy interpretation below the workbench only if they are still useful as secondary sections. The primary first screen must be the workbench.

- [ ] **Step 5: Run integration tests**

Run:

```bash
cd frontend && npx vitest run src/__tests__/SupplyChainBom.test.tsx src/__tests__/SupplyChainResearchWorkbench.test.tsx
```

Expected: PASS. If `SupplyChainBom.test.tsx` is too slow, run the new named test and the workbench test, then document the slow existing suite as residual risk.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SupplyChainBom.tsx frontend/src/__tests__/SupplyChainBom.test.tsx
git commit -m "feat: integrate supply chain research workbench"
```

---

### Task 7: Verification And Visual QA

**Files:**
- No production changes unless verification exposes a defect.

**Interfaces:**
- Consumes completed Tasks 1-6.
- Produces verification evidence and fixes for layout defects.

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
cd frontend && npx vitest run \
  src/__tests__/SupplyChainNodeNavigator.test.tsx \
  src/__tests__/SupplyChainCandidateGrid.test.tsx \
  src/__tests__/CompanyEvidencePanel.test.tsx \
  src/__tests__/SupplyChainResearchWorkbench.test.tsx \
  src/__tests__/SupplyChainMappingReviewPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run type check**

Run:

```bash
cd frontend && npx tsc -b --noEmit
```

Expected: PASS. If it fails on pre-existing `chartOptions.test.ts`, run a focused type check for changed files and record the existing failure:

```bash
cd frontend && npx tsc --noEmit --jsx react-jsx --moduleResolution bundler --module ESNext --target ES2020 --allowSyntheticDefaultImports --esModuleInterop --skipLibCheck \
  src/pages/SupplyChainBom.tsx \
  src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx \
  src/pages/supply-chain-bom/SupplyChainNodeNavigator.tsx \
  src/pages/supply-chain-bom/SupplyChainCandidateGrid.tsx \
  src/pages/supply-chain-bom/CandidateCompareBar.tsx \
  src/pages/supply-chain-bom/CompanyEvidencePanel.tsx \
  src/pages/supply-chain-bom/types.ts \
  src/api/client.ts
```

- [ ] **Step 3: Start dev server**

Run:

```bash
cd frontend && npm run dev -- --host 127.0.0.1 --port 3004
```

Expected: Vite reports `Local: http://127.0.0.1:3004/`.

- [ ] **Step 4: Visual QA**

Open `http://127.0.0.1:3004/` and navigate to the supply-chain page. Verify:

- Three columns show on desktop width.
- Core candidate table cells do not wrap awkwardly.
- Clicking a node changes candidates.
- Clicking a candidate fills the evidence panel.
- Selecting two candidates shows the compare bar.
- Narrow viewport stacks node, candidate, evidence in order without overlap.

- [ ] **Step 5: Run whitespace check**

Run:

```bash
git diff --check -- frontend/src/pages/SupplyChainBom.tsx frontend/src/pages/supply-chain-bom frontend/src/__tests__
```

Expected: no output.

- [ ] **Step 6: Final commit or report**

If any verification fix was needed:

```bash
git add frontend/src/pages frontend/src/__tests__ frontend/src/api/client.ts
git commit -m "fix: polish supply chain workbench layout"
```

If no fix was needed, report the verification evidence in the final response.

---

## Self-Review

- Spec coverage: left node drilldown is Task 3, candidate comparison is Task 2, evidence and review is Task 4, container integration is Tasks 5-6, verification is Task 7.
- Placeholder scan: no unresolved markers or open-ended implementation steps.
- Type consistency: `CandidateCompany`, `SupplyChainMappingQuality`, and review decision signatures match the current API client conventions and spec.
- Scope check: this is one frontend subsystem. Backend/schema/model changes are out of scope except optional compatible field consumption.
