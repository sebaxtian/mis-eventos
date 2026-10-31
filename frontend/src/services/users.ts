import apiClient from '@/services/api'
import type {
  AdminUserUpdatePayload,
  AuthUser,
  UserListParams,
  UserListResponse,
} from '@/types/api'

export async function listUsers(
  params: UserListParams = {},
): Promise<UserListResponse> {
  const response = await apiClient.get<UserListResponse>('/users', {
    params,
  })
  return response.data
}

export async function getUser(userId: number): Promise<AuthUser> {
  const response = await apiClient.get<AuthUser>(`/users/${userId}`)
  return response.data
}

export async function updateUser(
  userId: number,
  payload: AdminUserUpdatePayload,
): Promise<AuthUser> {
  const response = await apiClient.patch<AuthUser>(`/users/${userId}`, payload)
  return response.data
}
