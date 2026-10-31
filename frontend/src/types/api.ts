export type UserRole = 'ADMIN' | 'ORGANIZER' | 'ATTENDEE'

export interface AuthUser {
  id: number
  email: string
  full_name?: string
  role: UserRole
}

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
