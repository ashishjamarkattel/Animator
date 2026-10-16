import { useState } from 'react'
import type { Example } from '../lib/examples'
import { Icon } from './Icon'

/** Shows the silent animated preview; swaps in the narrated video when clicked. */
export function ExamplePlayer({ example }: { example: Example }) {
  const [playing, setPlaying] = useState(false)

  return (
    <figure className="example">
      {playing ? (
        <video src={example.video} controls autoPlay />
      ) : (
        <button className="example-preview" onClick={() => setPlaying(true)}>
          <img src={example.poster} alt="" />
          <span className="play-badge">
            <Icon name="play" size={16} />
            Play with sound
          </span>
        </button>
      )}
      <figcaption>
        <strong>{example.title}</strong>
        <span className="example-prompt">“{example.prompt}”</span>
        <span className="muted">
          {example.scenes} scenes, {example.length}
        </span>
      </figcaption>
    </figure>
  )
}
