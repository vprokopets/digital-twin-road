/**
 * Shared Axios HTTP client configured for local Vite development (`http://localhost:8000`)
 * or relative same-origin Nginx proxying in production bundles.
 */
import axios from 'axios'

const defaultBaseURL = import.meta.env.VITE_API_URL !== undefined
    ? import.meta.env.VITE_API_URL
    : (import.meta.env.DEV ? 'http://localhost:8000' : '')

const apiClient = axios.create({
    baseURL: defaultBaseURL,
    headers: {
        'Content-type': 'application/json',
    },
})

export default apiClient
