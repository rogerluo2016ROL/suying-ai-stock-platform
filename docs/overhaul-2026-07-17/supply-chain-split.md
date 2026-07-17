# supply-chain + screener + chain 拆分执行清单

> 2026-07-17 会话整理。client.ts 已拆 13/15 域(http + 12),剩这 3 域(supply-chain 交织块)。
> 下次清醒时按此执行,~30 分钟。**风险点:282 行类型块 Edit,务必分小段。**

## 0. 前置确认

```bash
cd frontend
wc -l src/api/client.ts          # 应 ~851 行(拆 12 域后)
ls src/api/domains/              # 应有 8 域:admin alert health market prediction signal trade workbench
```

## 1. 新建文件结构(6 个)

```
api/domains/
  supply-chain/
    types.ts    # 18 类型
    build.ts    # 4 个 build 辅助(加 export)
  screener/
    api.ts      # screenerApi
  chain/
    api.ts      # chainApi
    types.ts    # PolicyInterpret* / ChainDeconstruct* / ChainNodeCompanies*
```

## 2. 内容归属(client.ts → 哪个域)

### supply-chain/types.ts(18 个)
- `SupplyChainWorkbenchParams`(`type ... = number | {...}`)
- `SupplyChainCandidateRankingParams` / `Item` / `Response`
- `SupplyChainCapexEvidenceReviewQueueParams`
- `SupplyChainMappingReviewStatus` / `QueueParams` / `Item` / `Quality` / `ReviewDecision`
- `EvidenceChainDocument` / `Fact` / `Freshness` / `StageTransition` / `Expectation` / `Response`
- `EvidenceReviewQueueResponse`
- `CapexEvidenceReviewItem` / `QueueResponse` / `Request`

### supply-chain/build.ts(4 个,当前 `const xxx = (params) => {...}`,移时加 `export`)
- `buildSupplyChainWorkbenchPath`
- `buildSupplyChainMappingReviewQueuePath`
- `buildSupplyChainCandidateRankingPath`
- `buildSupplyChainCapexEvidenceReviewQueuePath`

### chain/types.ts(client.ts 内嵌,非 types.ts)
- `PolicyInterpretRequest` / `PolicyInterpretResponse`
- `ChainDeconstructResponse`
- `ChainNodeCompaniesResponse`

> 注:`ChainCandidate` / `ChainCandidatesResponse` / `SupplyChainBomResponse` / `ChainNode` 已在 `api/types.ts`,不要重复移。

## 3. 跨域 import

**screener/api.ts**:
```ts
import { api } from '../../http'
import type { AxiosResponse } from 'axios'
import type { SupplyChainWorkbenchParams, SupplyChainCandidateRankingParams, /* ...按需 */ } from '../supply-chain/types'
import { buildSupplyChainWorkbenchPath, buildSupplyChainCandidateRankingPath, buildSupplyChainMappingReviewQueuePath, buildSupplyChainCapexEvidenceReviewQueuePath } from '../supply-chain/build'
import type { ScreenerModesResponse, /* 共享 */ } from '../../types'
```

**chain/api.ts**:
```ts
import { api } from '../../http'
import type { AxiosResponse } from 'axios'
import { buildSupplyChainWorkbenchPath } from '../supply-chain/build'
import type { PolicyInterpretResponse, ChainDeconstructResponse, ChainNodeCompaniesResponse } from './types'
import type { ChainCandidate, ChainCandidatesResponse } from '../../types'
```

## 4. client.ts 改动

删:supply-chain 类型块 + 4 build + `screenerApi` + `chainApi` + chain 内嵌类型(PolicyInterpret 等)。

加 re-export(保持向后兼容,现有 `from 'client'` 的导入不破):
```ts
export type {
  SupplyChainWorkbenchParams,
  SupplyChainCandidateRankingParams, SupplyChainCandidateRankingItem, SupplyChainCandidateRankingResponse,
  SupplyChainCapexEvidenceReviewQueueParams,
  SupplyChainMappingReviewStatus, SupplyChainMappingReviewQueueParams, SupplyChainMappingReviewItem,
  SupplyChainMappingQuality, SupplyChainMappingReviewDecision,
  EvidenceChainDocument, EvidenceChainFact, EvidenceChainFreshness, EvidenceChainStageTransition,
  EvidenceChainExpectation, EvidenceChainResponse,
  EvidenceReviewQueueResponse,
  CapexEvidenceReviewItem, CapexEvidenceReviewQueueResponse, CapexEvidenceReviewRequest,
} from './domains/supply-chain/types'

export {
  buildSupplyChainWorkbenchPath, buildSupplyChainMappingReviewQueuePath,
  buildSupplyChainCandidateRankingPath, buildSupplyChainCapexEvidenceReviewQueuePath,
} from './domains/supply-chain/build'

export { screenerApi } from './domains/screener/api'

export { chainApi } from './domains/chain/api'

export type {
  PolicyInterpretRequest, PolicyInterpretResponse,
  ChainDeconstructResponse, ChainNodeCompaniesResponse,
} from './domains/chain/types'
```

## 5. 验证(避免管道 exit 误判,用直接重定向)

```bash
cd frontend
npx tsc -b --noEmit > /tmp/tsc.log 2>&1; echo "tsc=$?"
npx vitest run --exclude='tests/sit/**' > /tmp/vitest.log 2>&1; echo "vitest=$?"
# 两者都 0 才提交
```

## 6. 注意事项

1. **screenerApi 含 supply-chain 方法**(`getSupplyChainThemes`/`Bom`/`Workbench`/`CandidateRanking`/`Node`/`Company`/`MappingQuality`/`MappingReviewQueue`/`EvidenceChain`/`EvidenceReviewQueue`/`CapexEvidenceReviewQueue`/`reviewCapexEvidence`/`reviewMapping`/`extractFacts`)—— **保持 screenerApi 对象结构不变**(组件经 `screenerApi.getSupplyChain*` 调用),只把类型/辅助移到 supply-chain 域,不改调用方。
2. **282 行类型块 Edit 风险高** → 按类型组分多次小 Edit(如 EvidenceChain* 一组、Capex* 一组、SupplyChainMapping* 一组),每次 old_string 控制在 30-60 行。不要一次 282 行 old。
3. **chainApi 的 `getCandidates`** 内联了 `ChainCandidate[]` 断言 + `buildSupplyChainWorkbenchPath`,迁移时保持逻辑。
4. **build 辅助是箭头函数** `const buildXxx = (params) => {...}`,非 `function`,移到 build.ts 加 `export const`。
5. **ErrorBoundary.test 全套并发偶发 flaky**(单独跑稳定)—— 若 vitest 报 1 failed 且是该测试,非本次引入,可重跑确认。

## 7. 提交

```bash
git add frontend/src/api/domains/supply-chain/ frontend/src/api/domains/screener/ frontend/src/api/domains/chain/ frontend/src/api/client.ts
git commit -m "refactor(frontend): extract supply-chain/screener/chain domains (波2-C 域拆分 #8, 完结)"
```

完成后 client.ts 应 ~450 行,C 域拆分 15/15 完结。
