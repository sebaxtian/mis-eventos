import apiClient from '@/services/api'
import type {
  AuthUser,
  LoginPayload,
  LoginResponse,
  RegisterPayload,
  UpdateProfilePayload,
} from '@/types/api'

export async function register(payload: RegisterPayload): Promise<AuthUser> {
  const response = await apiClient.post<AuthUser>('/auth/register', payload)
  return response.data
}

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>('/auth/login', payload)
  return response.data
}

export async function getMe(): Promise<AuthUser> {
  const response = await apiClient.get<AuthUser>('/auth/me')
  return response.data
}

export async function updateMe(
  payload: UpdateProfilePayload,
): Promise<AuthUser> {
  const response = await apiClient.patch<AuthUser>('/auth/me', payload)
  return response.data
}

export const registerUser = register
export const loginUser = login
