export type UserRole = 'ADMIN' | 'ORGANIZER' | 'ATTENDEE'

export interface AuthUser {
  id: number
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface RegisterPayload {
  email: string
  password: string
  full_name: string
}

export interface LoginPayload {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}

export interface UpdateProfilePayload {
  full_name: string
}

export interface AdminUserUpdatePayload {
  full_name?: string
  role?: UserRole
  is_active?: boolean
}

export interface UserListParams {
  page?: number
  size?: number
  role?: UserRole
  is_active?: boolean
}

export type UserListResponse = PaginatedResponse<AuthUser>

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export interface ValidationFieldError {
  field: string
  message: string
}

export interface ApiError {
  detail: string
  errors?: ValidationFieldError[]
}

export interface HealthResponse {
  status: 'ok'
  database: 'ok'
  redis: 'ok' | 'degraded'
}

export type EventStatus = 'DRAFT' | 'PUBLISHED' | 'CANCELLED'

export interface EventImageUrls {
  w400: string
  w800: string
  w1200: string
}

export interface EventRead {
  id: number
  title: string
  description: string
  date: string
  total_capacity: number
  registered_count: number
  available_capacity: number
  status: EventStatus
  organizer_id: number
  image_urls: EventImageUrls | null
  created_at: string
  updated_at: string
}

export interface EventCreatePayload {
  title: string
  description: string
  date: string
  total_capacity: number
  status?: 'DRAFT' | 'PUBLISHED'
}

export interface EventUpdatePayload {
  title?: string
  description?: string
  date?: string
  total_capacity?: number
  status?: EventStatus
}

export interface EventListQuery {
  page?: number
  size?: number
  search?: string
  status?: EventStatus
  mine?: boolean
}

export type EventListResponse = PaginatedResponse<EventRead>

export interface SessionRead {
  id: number
  event_id: number
  title: string
  description: string | null
  speaker: string
  start_time: string
  end_time: string
  capacity: number
  registered_count: number
  available_capacity: number
  created_at: string
  updated_at: string
}

export interface SessionListResponse {
  items: SessionRead[]
  total: number
}

export interface SessionCreatePayload {
  title: string
  speaker: string
  description?: string | null
  start_time: string
  end_time: string
  capacity: number
}

export interface SessionUpdatePayload {
  title?: string
  speaker?: string
  description?: string | null
  start_time?: string
  end_time?: string
  capacity?: number
}
