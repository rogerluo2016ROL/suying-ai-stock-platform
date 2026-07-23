/** Admin 域类型 (从 client.ts 拆出, C 域拆分)。 */

export interface MembershipInfo {
  status: string
  plan?: string | null
  starts_at?: string | null
  ends_at?: string | null
  source?: string | null
  note?: string | null
  is_member: boolean
  days_remaining?: number | null
}

export interface AdminUser {
  id: number
  name: string
  email: string
  role: string
  is_active: boolean
  created_at: string
  updated_at: string
  permissions?: string[]
  membership?: MembershipInfo | null
}

export interface AdminUsersResponse {
  total: number
  page: number
  page_size: number
  users: AdminUser[]
}

export interface PermissionItem {
  key: string
  label: string
  group: string
  description: string
  enabled: boolean
}

export interface RolePermissions {
  role: string
  label: string
  description?: string | null
  permissions: PermissionItem[]
}

export interface RolePermissionsListResponse {
  roles: RolePermissions[]
}

export interface MembershipUser {
  id: number
  name: string
  email: string
  role: string
  is_active: boolean
  created_at: string
  updated_at: string
  membership: MembershipInfo
}

export interface MembershipsResponse {
  total: number
  page: number
  page_size: number
  members: MembershipUser[]
}

export interface UserAuthorizationPayload {
  role?: string
  is_active?: boolean
  membership?: {
    status?: string
    plan?: string | null
    starts_at?: string | null
    ends_at?: string | null
    source?: string | null
    note?: string | null
  }
}
