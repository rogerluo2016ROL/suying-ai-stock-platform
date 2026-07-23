import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  AdminUsersResponse,
  RolePermissionsListResponse,
  RolePermissions,
  UserAuthorizationPayload,
  AdminUser,
  MembershipsResponse,
} from './types'

/** Admin 域 API (从 client.ts 拆出, C 域拆分)。 */
export const adminApi = {
  getUsers: (params: {
    page?: number
    page_size?: number
    role?: string
    is_active?: boolean
    q?: string
  } = {}): Promise<AxiosResponse<AdminUsersResponse>> =>
    api.get('/admin/users', { params }),

  getRolePermissions: (): Promise<AxiosResponse<RolePermissionsListResponse>> =>
    api.get('/admin/permissions/roles'),

  updateRolePermissions: (
    role: string,
    permissionKeys: string[],
  ): Promise<AxiosResponse<RolePermissions>> =>
    api.put(`/admin/permissions/roles/${encodeURIComponent(role)}`, {
      permission_keys: permissionKeys,
    }),

  updateUserAuthorization: (
    userId: number,
    payload: UserAuthorizationPayload,
  ): Promise<AxiosResponse<AdminUser>> =>
    api.put(`/admin/users/${userId}/authorization`, payload),

  getMemberships: (params: {
    page?: number
    page_size?: number
    status?: string
    q?: string
  } = {}): Promise<AxiosResponse<MembershipsResponse>> =>
    api.get('/admin/memberships', { params }),
}
