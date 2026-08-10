import { useState } from 'react'
import { Alert } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import { screenerApi } from '../api/client'
import { DataFreshnessBar, MetricCard, PrototypePage, PrototypePageHeader, PrototypeTabs } from '../components/prototype'
import CompanyResearchDrawer from './supply-chain-bom/CompanyResearchDrawer'
import SupplyChainMappingReviewPanel from './supply-chain-bom/SupplyChainMappingReviewPanel'
import SupplyChainResearchWorkbench from './supply-chain-bom/SupplyChainResearchWorkbench'
import SupplyChainCandidateRankingPanel from './supply-chain-bom/SupplyChainCandidateRankingPanel'
import SupplyChainCapexEvidenceReviewPanel from './supply-chain-bom/SupplyChainCapexEvidenceReviewPanel'
import ChainDeconstructSection from './supply-chain-bom/ChainDeconstructSection'
import NodeResearchSection from './supply-chain-bom/NodeResearchSection'
import CandidatePoolSection from './supply-chain-bom/CandidatePoolSection'
import UpstreamPoolSection from './supply-chain-bom/UpstreamPoolSection'
import PolicyInterpretSection from './supply-chain-bom/PolicyInterpretSection'
import { useSupplyChainWorkbench } from './supply-chain-bom/useSupplyChainWorkbench'
import type { CandidateCompany } from './supply-chain-bom/types'
import { activeSupplyChainTab, researchCollectionLabel, supplyChainTabs } from './supply-chain-bom/helpers'

export default function SupplyChainBom() {
  const location = useLocation()
  const navigate = useNavigate()
  const {
    themes, nodes, edges, model, nodeCandidates, upstreamCandidates, selectedNodeThesis,
    dataFreshness, researchIngestion, selectedThemeId, selectedNodeId, nodeDetail,
    loading, candidateLoading, mappingQuality, mappingQualityError, workbenchError,
    catalogSource, chainOverlays, chainTemplate, chainDeconstructResult, chainLoading,
    chainDeconstructError, selectedTheme, selectedNode, filteredNodes, activeCandidates,
    methodSummary, setChainOverlays, setChainTemplate, selectTheme, selectNode,
    selectNodeById, reviewMapping, addThemes,
  } = useSupplyChainWorkbench()

  const [companyDetail, setCompanyDetail] = useState<CandidateCompany | null>(null)
  const [companyOpen, setCompanyOpen] = useState(false)

  const openCompany = (company: CandidateCompany) => {
    setCompanyDetail(company)
    setCompanyOpen(true)
    screenerApi.getSupplyChainCompany(company.code).then(resp => {
      setCompanyDetail({ ...company, ...(resp.data as unknown as Record<string, unknown>) })
    })
  }

  const activeModuleKey = activeSupplyChainTab(location.pathname)
  const activeModuleTab = supplyChainTabs.find(tab => tab.key === activeModuleKey) || supplyChainTabs[1]

  return (
    <PrototypePage className="supply-chain-prototype">
      <PrototypeTabs
        ariaLabel="产业链拆解页签"
        activeKey={activeModuleKey}
        onChange={(key) => {
          const tab = supplyChainTabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={supplyChainTabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`产业链拆解 - ${activeModuleTab.label}`}
        subtitle="政策证据 · 三模式解构 · 公司映射 · 研究闭环"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={dataFreshness.market?.latest_trade_date}
            updatedAt={dataFreshness.research_reports?.latest_pub_date || dataFreshness.market?.latest_trade_date}
            source={catalogSource}
          />
        )}
        actions={[
          { key: 'public', label: '公共产业图谱', active: true, tone: 'neutral' },
          { key: 'private', label: '账户私有观察池', tone: 'up' },
          { key: 'research', label: researchCollectionLabel(researchIngestion.auto_collection_status), tone: 'warn' },
        ]}
      />
      <div className="kpis">
        <MetricCard label="当前主题" value={selectedTheme?.name || selectedNode?.policy_theme || '政策主题'} sub={model.name || '产业链解构选股模型 V4'} tone="accent" />
        <MetricCard label="候选公司" value={activeCandidates.length} sub={upstreamCandidates.length ? `上游观察 ${upstreamCandidates.length}` : '全局观察池'} tone="up" />
        <MetricCard label="BOM 节点" value={nodes.length} sub={`当前模式：${methodSummary.title}`} tone="muted" />
        <MetricCard label="数据更新" value={dataFreshness.market?.latest_trade_date || '--'} sub={dataFreshness.research_reports?.latest_pub_date ? `研报 ${dataFreshness.research_reports.latest_pub_date}` : '等待数据同步'} tone="warn" />
      </div>

      {workbenchError && (
        <Alert
          type="warning"
          showIcon
          message="组合工作台接口不可用"
          description={workbenchError}
          style={{ marginBottom: 16 }}
        />
      )}

      {mappingQualityError && (
        <Alert
          type="warning"
          showIcon
          message="映射质量接口不可用"
          description={mappingQualityError}
          style={{ marginBottom: 16 }}
        />
      )}

      {chainDeconstructError && (
        <Alert
          type="error"
          showIcon
          message="产业链拆解接口不可用"
          description={chainDeconstructError}
          style={{ marginBottom: 16 }}
        />
      )}

      {activeModuleKey === 'capex-review' ? (
        <SupplyChainCapexEvidenceReviewPanel />
      ) : activeModuleKey === 'ranking' ? (
        <SupplyChainCandidateRankingPanel onOpenCompany={openCompany} />
      ) : (
        <>
          <SupplyChainResearchWorkbench
            themes={themes}
            nodes={nodes}
            candidates={activeCandidates}
            selectedThemeId={selectedThemeId}
            selectedNodeId={selectedNodeId}
            selectedNodeThesis={selectedNodeThesis}
            mappingQuality={mappingQuality}
            chainTemplate={chainTemplate}
            templateResult={chainDeconstructResult}
            loading={loading || candidateLoading}
            onChainTemplateChange={setChainTemplate}
            onSelectTheme={selectTheme}
            onSelectNode={selectNodeById}
            onOpenCompany={openCompany}
            onReviewMapping={reviewMapping}
          />

          <ChainDeconstructSection
            themes={themes}
            nodes={nodes}
            edges={edges}
            filteredNodes={filteredNodes}
            selectedThemeId={selectedThemeId}
            selectedNodeId={selectedNodeId}
            selectedTheme={selectedTheme}
            model={model}
            nodeDetail={nodeDetail}
            activeCandidateCount={activeCandidates.length}
            chainOverlays={chainOverlays}
            chainLoading={chainLoading}
            chainDeconstructResult={chainDeconstructResult}
            loading={loading}
            onSelectTheme={selectTheme}
            onSelectNode={selectNode}
            onOverlaysChange={setChainOverlays}
          />

          <NodeResearchSection
            nodes={filteredNodes}
            selectedNode={selectedNode}
            selectedNodeThesis={selectedNodeThesis}
            selectedTheme={selectedTheme}
            candidateCount={nodeCandidates.length}
            nodeDetail={nodeDetail}
            chainOverlays={chainOverlays}
            onSelectNode={selectNode}
          />

          <CandidatePoolSection
            fallbackCandidates={activeCandidates}
            workbenchLoading={candidateLoading}
            selectedNode={selectedNode}
            mappingMessage={selectedNodeThesis.mapping_message}
            themeName={selectedTheme?.name || selectedNode?.policy_theme}
            onOpenCompany={openCompany}
          />

          <div style={{ marginTop: 16 }}>
            <SupplyChainMappingReviewPanel />
          </div>

          <UpstreamPoolSection
            candidates={upstreamCandidates}
            onOpenCompany={openCompany}
          />

          <PolicyInterpretSection
            researchIngestion={researchIngestion}
            onAddThemes={addThemes}
          />
        </>
      )}

      <CompanyResearchDrawer
        open={companyOpen}
        company={companyDetail}
        onClose={() => setCompanyOpen(false)}
      />
    </PrototypePage>
  )
}
