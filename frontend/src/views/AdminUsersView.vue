<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { AxiosError } from 'axios'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseSkeleton from '@/components/base/BaseSkeleton.vue'
import { listUsers, updateUser } from '@/services/users'
import { useAuthStore } from '@/stores/auth'
import type {
  ApiError,
  AuthUser,
  UserListParams,
  UserRole,
} from '@/types/api'

interface EditableUserRow {
  full_name: string
  role: UserRole
  is_active: boolean
  saving: boolean
}

const authStore = useAuthStore()

const users = ref<AuthUser[]>([])
const edits = reactive<Record<number, EditableUserRow>>({})
const page = ref(1)
const size = ref(10)
const total = ref(0)
const pages = ref(0)
const roleFilter = ref<'' | UserRole>('')
const activeFilter = ref<'' | 'true' | 'false'>('')
const isLoading = ref(false)
const feedbackMessage = ref('')
const feedbackType = ref<'success' | 'error'>('success')

function syncEditableRows(list: AuthUser[]): void {
  for (const item of list) {
    edits[item.id] = {
      full_name: item.full_name,
      role: item.role,
      is_active: item.is_active,
      saving: false,
    }
  }
}

async function fetchUsers(): Promise<void> {
  isLoading.value = true
  try {
    const params: UserListParams = {
      page: page.value,
      size: size.value,
    }
    if (roleFilter.value) {
      params.role = roleFilter.value
    }
    if (activeFilter.value === 'true') {
      params.is_active = true
    } else if (activeFilter.value === 'false') {
      params.is_active = false
    }
    const response = await listUsers(params)
    users.value = response.items
    total.value = response.total
    pages.value = response.pages
    syncEditableRows(response.items)
  } catch (err: unknown) {
    const axiosErr = err as AxiosError<ApiError>
    feedbackType.value = 'error'
    feedbackMessage.value =
      axiosErr.response?.data?.detail ||
      'No se pudo cargar el listado de usuarios'
  } finally {
    isLoading.value = false
  }
}

async function onFilterChange(): Promise<void> {
  page.value = 1
  await fetchUsers()
}

async function changePage(nextPage: number): Promise<void> {
  if (nextPage < 1 || (pages.value > 0 && nextPage > pages.value)) return
  page.value = nextPage
  await fetchUsers()
}

async function onSaveUser(user: AuthUser): Promise<void> {
  const row = edits[user.id]
  if (!row) return

  feedbackMessage.value = ''
  row.saving = true
  try {
    const isSelf = authStore.user?.id === user.id
    const payload = isSelf
      ? { full_name: row.full_name.trim() }
      : {
          full_name: row.full_name.trim(),
          role: row.role,
          is_active: row.is_active,
        }
    const updated = await updateUser(user.id, payload)
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx !== -1) {
      users.value[idx] = updated
    }
    syncEditableRows(users.value)
    if (isSelf && authStore.token) {
      authStore.setSession(authStore.token, updated)
    }
    feedbackType.value = 'success'
    feedbackMessage.value = 'Usuario actualizado correctamente'
  } catch (err: unknown) {
    const axiosErr = err as AxiosError<ApiError>
    const fieldMsg = axiosErr.response?.data?.errors?.[0]?.message
    const detail = axiosErr.response?.data?.detail
    feedbackType.value = 'error'
    feedbackMessage.value =
      fieldMsg || detail || 'No se pudo actualizar el usuario'
  } finally {
    row.saving = false
  }
}

onMounted(() => {
  void fetchUsers()
})
</script>

<template>
  <main class="mx-auto max-w-5xl p-6">
    <h1 class="text-2xl font-bold text-slate-900">
      Administración de usuarios
    </h1>
    <p class="mt-1 text-sm text-slate-600">
      Gestiona nombres, roles y estado de activación de las cuentas registradas.
    </p>

    <BaseAlert
      v-if="feedbackMessage"
      :type="feedbackType"
      :message="feedbackMessage"
      dismissible
      class="mt-4"
      @dismiss="feedbackMessage = ''"
    />

    <section class="mt-6 flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <label for="filter-role" class="block text-xs font-semibold text-slate-600">
          Filtrar por rol
        </label>
        <select
          id="filter-role"
          v-model="roleFilter"
          class="mt-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          @change="onFilterChange"
        >
          <option value="">Todos los roles</option>
          <option value="ADMIN">Administrador</option>
          <option value="ORGANIZER">Organizador</option>
          <option value="ATTENDEE">Asistente</option>
        </select>
      </div>

      <div>
        <label for="filter-active" class="block text-xs font-semibold text-slate-600">
          Estado
        </label>
        <select
          id="filter-active"
          v-model="activeFilter"
          class="mt-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          @change="onFilterChange"
        >
          <option value="">Todos</option>
          <option value="true">Activos</option>
          <option value="false">Inactivos</option>
        </select>
      </div>
    </section>

    <div v-if="isLoading" class="mt-6">
      <BaseSkeleton :lines="4" />
    </div>

    <div
      v-else-if="users.length === 0"
      class="mt-6 rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-600"
    >
      No se encontraron usuarios con los criterios seleccionados.
    </div>

    <div
      v-else
      class="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm"
    >
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
          <tr>
            <th class="px-4 py-3">Correo</th>
            <th class="px-4 py-3">Nombre</th>
            <th class="px-4 py-3">Rol</th>
            <th class="px-4 py-3">Activo</th>
            <th class="px-4 py-3 text-right">Acciones</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="u in users" :key="u.id">
            <td class="px-4 py-3 font-medium text-slate-900">
              {{ u.email }}
            </td>
            <td class="px-4 py-3">
              <input
                v-if="edits[u.id]"
                v-model="edits[u.id].full_name"
                type="text"
                :data-testid="`full-name-input-${u.id}`"
                class="w-full rounded border border-slate-300 px-2 py-1 text-sm"
              />
            </td>
            <td class="px-4 py-3">
              <select
                v-if="edits[u.id]"
                v-model="edits[u.id].role"
                :disabled="authStore.user?.id === u.id"
                :data-testid="`role-select-${u.id}`"
                class="rounded border border-slate-300 px-2 py-1 text-sm disabled:opacity-60"
              >
                <option value="ADMIN">Administrador</option>
                <option value="ORGANIZER">Organizador</option>
                <option value="ATTENDEE">Asistente</option>
              </select>
            </td>
            <td class="px-4 py-3">
              <input
                v-if="edits[u.id]"
                v-model="edits[u.id].is_active"
                type="checkbox"
                :disabled="authStore.user?.id === u.id"
                :data-testid="`active-checkbox-${u.id}`"
                class="h-4 w-4 rounded border-slate-300 text-indigo-600"
              />
            </td>
            <td class="px-4 py-3 text-right">
              <BaseButton
                v-if="edits[u.id]"
                type="button"
                :is-loading="edits[u.id].saving"
                :data-testid="`save-user-${u.id}`"
                @click="onSaveUser(u)"
              >
                Guardar
              </BaseButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-if="pages > 1"
      class="mt-4 flex items-center justify-between text-sm text-slate-600"
    >
      <span>Página {{ page }} de {{ pages }} ({{ total }} usuarios)</span>
      <div class="flex gap-2">
        <BaseButton
          type="button"
          variant="secondary"
          :disabled="page <= 1"
          @click="changePage(page - 1)"
        >
          Anterior
        </BaseButton>
        <BaseButton
          type="button"
          variant="secondary"
          :disabled="page >= pages"
          @click="changePage(page + 1)"
        >
          Siguiente
        </BaseButton>
      </div>
    </div>
  </main>
</template>
