import { useEffect, useRef } from 'react'
import { Icon } from '../components/Icon'

interface Props {
  title: string
  src: string
  onClose: () => void
}

export function PlayerModal({ title, src, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    dialog.current?.showModal()
  }, [])

  return (
    <dialog
      ref={dialog}
      className="player"
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && dialog.current.close()}
    >
      <div className="player-head">
        <h2>{title}</h2>
        <button className="icon-btn" onClick={() => dialog.current?.close()} aria-label="Close player">
          <Icon name="close" />
        </button>
      </div>
      <video src={src} controls autoPlay />
    </dialog>
  )
}
