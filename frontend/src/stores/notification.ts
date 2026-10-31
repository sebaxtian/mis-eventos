import { ref } from 'vue'
import { defineStore } from 'pinia'

export type NotificationType = 'success' | 'error' | 'warning' | 'info'

export interface NotificationItem {
  id: number
  type: NotificationType
  message: string
}

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<NotificationItem[]>([])
  const lastMessage = ref<string | null>(null)
  const lastType = ref<NotificationType | null>(null)
  let nextId = 1

  function notify(message: string, type: NotificationType = 'info'): void {
    lastMessage.value = message
    lastType.value = type
    notifications.value.push({
      id: nextId++,
      type,
      message,
    })
  }

  function clear(): void {
    notifications.value = []
    lastMessage.value = null
    lastType.value = null
  }

  return {
    notifications,
    lastMessage,
    lastType,
    notify,
    clear,
  }
})
