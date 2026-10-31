import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { AuthUser, UserListResponse } from '@/types/api'
import apiClient from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import AdminUsersView from '@/views/AdminUsersView.vue'

const adminUser: AuthUser = {
  id: 1,
  email: 'admin@example.com',
  full_name: 'Admin Principal',
  role: 'ADMIN',
  is_active: true,
  created_at: '2026-10-31T10:00:00Z',
  updated_at: '2026-10-31T10:00:00Z',
}

const attendeeUser: AuthUser = {
  id: 2,
  email: 'ana@example.com',
  full_name: 'Ana Pérez',
  role: 'ATTENDEE',
  is_active: true,
  created_at: '2026-10-31T11:00:00Z',
  updated_at: '2026-10-31T11:00:00Z',
}

const initialPage: UserListResponse = {
  items: [adminUser, attendeeUser],
  total: 2,
  page: 1,
  size: 10,
  pages: 1,
}

describe('AdminUsersView user management', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('AUTH-AC-15 admin users view lists paginated users and updates role/is_active', async () => {
    const authStore = useAuthStore()
    authStore.setSession('jwt-admin-15', adminUser)

    const getSpy = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValueOnce({ data: initialPage })
      .mockResolvedValueOnce({
        data: {
          items: [attendeeUser],
          total: 1,
          page: 1,
          size: 10,
          pages: 1,
        },
      })

    const updatedAttendee: AuthUser = {
      ...attendeeUser,
      full_name: 'Ana Organiza',
      role: 'ORGANIZER',
      is_active: false,
    }
    const patchSpy = vi
      .spyOn(apiClient, 'patch')
      .mockResolvedValueOnce({ data: updatedAttendee })

    const wrapper = mount(AdminUsersView)
    await flushPromises()

    expect(getSpy).toHaveBeenCalledWith('/users', {
      params: { page: 1, size: 10 },
    })
    expect(wrapper.text()).toContain('admin@example.com')
    expect(wrapper.text()).toContain('ana@example.com')
    expect(wrapper.text()).not.toContain('Eliminar')

    await wrapper.find('select#filter-role').setValue('ATTENDEE')
    await flushPromises()

    expect(getSpy).toHaveBeenLastCalledWith('/users', {
      params: { page: 1, size: 10, role: 'ATTENDEE' },
    })

    await wrapper
      .find(`input[data-testid="full-name-input-${attendeeUser.id}"]`)
      .setValue('Ana Organiza')
    await wrapper
      .find(`select[data-testid="role-select-${attendeeUser.id}"]`)
      .setValue('ORGANIZER')
    await wrapper
      .find(`input[data-testid="active-checkbox-${attendeeUser.id}"]`)
      .setValue(false)
    await wrapper
      .find(`button[data-testid="save-user-${attendeeUser.id}"]`)
      .trigger('click')
    await flushPromises()

    expect(patchSpy).toHaveBeenCalledWith(`/users/${attendeeUser.id}`, {
      full_name: 'Ana Organiza',
      role: 'ORGANIZER',
      is_active: false,
    })
    expect(wrapper.text()).toContain('Usuario actualizado correctamente')
  })
})
