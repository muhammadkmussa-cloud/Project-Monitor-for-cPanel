import { useState, useEffect, useCallback } from 'react'

const WS_BASE_URL = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

export function useWebSocket(path) {
  const [socket, setSocket] = useState(null)
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState(null)

  useEffect(() => {
    const wsUrl = `${WS_BASE_URL}//${window.location.host}${path}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      setIsConnected(true)
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setLastMessage(data)
    }

    ws.onclose = () => {
      setIsConnected(false)
      console.log('WebSocket disconnected')
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    setSocket(ws)

    return () => {
      ws.close()
    }
  }, [path])

  const sendMessage = useCallback((message) => {
    if (socket && isConnected) {
      socket.send(JSON.stringify(message))
    }
  }, [socket, isConnected])

  return { isConnected, lastMessage, sendMessage }
}

export default useWebSocket
