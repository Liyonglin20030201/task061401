import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import router from '../router'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      if (auth.refreshToken) {
        try {
          const res = await axios.post('/api/auth/refresh', {
            refresh_token: auth.refreshToken,
          })
          auth.setTokens(res.data.access_token, res.data.refresh_token)
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`
          return axios(error.config)
        } catch {
          auth.logout()
          router.push('/login')
        }
      } else {
        auth.logout()
        router.push('/login')
      }
    }
    return Promise.reject(error)
  }
)

export default api
