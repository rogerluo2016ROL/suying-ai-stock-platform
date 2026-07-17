/** Training 域类型 (从 client.ts 拆出, C 域拆分)。 */

export interface TrainingModelRecord {
  id: string
  name: string
  version: number
  model_type: string
  stage: string
  run_id?: string | null
  experiment_id?: string | null
  metrics?: Record<string, number>
  artifact_uri?: string | null
  deployed_at?: string | null
  deployed_by?: string | null
  created_by: string
  created_at: string
  updated_at?: string | null
  notes?: string | null
}

export interface TrainingModelsResponse {
  models: TrainingModelRecord[]
  total: number
  page: number
  page_size: number
}

export interface TrainingHistoryRecord {
  job_id: string
  model_type: string
  status: string
  params?: Record<string, unknown> | null
  final_metrics?: Record<string, number> | null
  model_uri?: string | null
  created_by: string
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  duration_seconds?: number | null
}

export interface TrainingHistoryResponse {
  jobs: TrainingHistoryRecord[]
  total: number
  page: number
  page_size: number
}

export interface TrainingScheduleResponse {
  enabled: boolean
  cron: string
  model_type: string
  params?: Record<string, unknown> | null
  auto_deploy: boolean
  next_run?: string | null
  last_run?: string | null
  last_job_id?: string | null
  last_job_status?: string | null
}

export interface TrainingModelActionResponse {
  model_id: string
  message: string
  stage?: string
  deployed_at?: string
  previous_production_version?: number | null
  new_production_version?: number
  rolled_back_from?: number
  reason?: string
}
