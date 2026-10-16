import { useState } from 'react'
import { EXAMPLES } from '../lib/examples'
import { ExamplePlayer } from './ExamplePlayer'
import { Icon } from './Icon'

/** Landing-only: the example videos in a gradient card, one tab per example. */
export function Showcase({ onStart }: { onStart: () => void }) {
  const [active, setActive] = useState(0)

  return (
    <section className="showcase" aria-label="Example videos">
      <div className="showcase-tabs" role="tablist">
        {EXAMPLES.map((example, i) => (
          <button key={example.title} role="tab" aria-selected={i === active} className="showcase-tab" onClick={() => setActive(i)}>
            {example.title}
          </button>
        ))}
      </div>
      <div className="showcase-stage">
        <ExamplePlayer key={active} example={EXAMPLES[active]} />
      </div>
      <button className="showcase-cta" onClick={onStart}>
        <Icon name="spark" size={20} />
        Create your first video
      </button>
    </section>
  )
}
