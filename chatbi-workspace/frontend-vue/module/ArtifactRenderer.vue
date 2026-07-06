<template>
  <div class="chatbi-artifact" v-if="artifactType">
    <div v-if="artifactType === 'table'" class="artifact-block">
      <div class="artifact-title">{{ title || '数据表' }}</div>
      <div class="artifact-table-wrap">
        <table class="artifact-table">
          <thead>
            <tr>
              <th v-for="column in columns" :key="column">{{ column }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
              <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else-if="artifactType === 'evidence'" class="artifact-block">
      <div class="artifact-title">{{ title || '证据链' }}</div>
      <div class="artifact-meta" v-if="payload.mapping_id">映射：{{ payload.mapping_id }}</div>
      <details class="evidence-item" v-for="(fact, index) in facts" :key="index">
        <summary>
          <span class="evidence-index">{{ index + 1 }}</span>
          <span>{{ fact.title || fact.summary || fact.fact_type || '证据' }}</span>
        </summary>
        <div class="evidence-body">
          <div v-if="fact.content || fact.fact_text">{{ fact.content || fact.fact_text }}</div>
          <div v-if="fact.source || fact.source_name" class="artifact-meta">来源：{{ fact.source || fact.source_name }}</div>
          <div v-if="fact.date || fact.published_at" class="artifact-meta">日期：{{ fact.date || fact.published_at }}</div>
          <div v-if="fact.confidence_score || fact.confidence" class="artifact-meta">置信度：{{ fact.confidence_score || fact.confidence }}</div>
        </div>
      </details>
      <div v-if="facts.length === 0" class="artifact-empty">暂无证据明细</div>
    </div>

    <div v-else-if="artifactType === 'company_card'" class="artifact-block company-card">
      <div class="artifact-title">{{ payload.company_name || payload.name || '公司卡片' }}</div>
      <div class="company-grid">
        <div v-for="item in companyItems" :key="item.label">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </div>

    <div v-else class="artifact-block">
      <div class="artifact-title">{{ title || artifactType }}</div>
      <pre>{{ prettyArtifact }}</pre>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ArtifactRenderer',
  props: {
    artifact: {
      type: Object,
      required: true
    }
  },
  computed: {
    artifactType() {
      return this.artifact.artifact_type || this.artifact.type || ''
    },
    payload() {
      return this.artifact.payload || {}
    },
    title() {
      return this.artifact.title || this.payload.title || ''
    },
    columns() {
      return this.payload.columns || []
    },
    rows() {
      return this.payload.rows || []
    },
    facts() {
      return this.payload.facts || this.payload.evidence || []
    },
    companyItems() {
      const keys = [
        ['stock_code', '代码'],
        ['chain_name', '产业链'],
        ['tag_name', '标签'],
        ['score', '综合分'],
        ['three_high_score', '三高分'],
        ['stage', '阶段']
      ]
      return keys
        .map(([key, label]) => ({ label, value: this.payload[key] }))
        .filter(item => item.value !== undefined && item.value !== null && String(item.value).length > 0)
    },
    prettyArtifact() {
      try {
        return JSON.stringify(this.artifact, null, 2)
      } catch (e) {
        return String(this.artifact)
      }
    }
  }
}
</script>

<style lang="less" scoped>
.chatbi-artifact {
  margin: 10px 0;
}

.artifact-block {
  border: 1px solid #e6edf7;
  border-radius: 8px;
  background: #ffffff;
  padding: 10px;
}

.artifact-title {
  color: #101828;
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
  margin-bottom: 8px;
}

.artifact-meta {
  color: #667085;
  font-size: 12px;
  line-height: 18px;
  margin-top: 4px;
}

.artifact-table-wrap {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.artifact-table {
  min-width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
}

.artifact-table th,
.artifact-table td {
  border: 1px solid #e6edf7;
  padding: 8px 10px;
  color: #344054;
  font-size: 12px;
  line-height: 18px;
  text-align: left;
}

.artifact-table th {
  background: #eef5ff;
  color: #175cd3;
  font-weight: 600;
}

.evidence-item {
  border-top: 1px solid #eef2f6;
  padding: 8px 0;
}

.evidence-item summary {
  align-items: center;
  color: #344054;
  cursor: pointer;
  display: flex;
  font-size: 13px;
  font-weight: 600;
  gap: 6px;
  line-height: 20px;
}

.evidence-index {
  align-items: center;
  background: #e8f3ff;
  border-radius: 50%;
  color: #1570ef;
  display: inline-flex;
  flex: 0 0 auto;
  font-size: 11px;
  height: 18px;
  justify-content: center;
  width: 18px;
}

.evidence-body {
  color: #475467;
  font-size: 12px;
  line-height: 20px;
  padding: 8px 0 2px 24px;
}

.artifact-empty {
  color: #98a2b3;
  font-size: 12px;
  line-height: 20px;
}

.company-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.company-grid div {
  background: #f8fafc;
  border-radius: 6px;
  padding: 8px;
}

.company-grid span {
  color: #667085;
  display: block;
  font-size: 11px;
  line-height: 16px;
}

.company-grid strong {
  color: #101828;
  display: block;
  font-size: 13px;
  line-height: 18px;
  margin-top: 2px;
}

pre {
  background: #f8fafc;
  border-radius: 6px;
  color: #344054;
  font-size: 12px;
  line-height: 18px;
  margin: 0;
  overflow-x: auto;
  padding: 8px;
}
</style>
