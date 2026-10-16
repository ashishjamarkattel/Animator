import beesGif from '../../../examples/how_bees_make_honey.gif'
import beesMp4 from '../../../examples/how_bees_make_honey.mp4'
import einsteinGif from '../../../examples/einstein_emc2.gif'
import einsteinMp4 from '../../../examples/einstein_emc2.mp4'
import photosynthesisGif from '../../../examples/photosynthesis.gif'
import photosynthesisMp4 from '../../../examples/photosynthesis.mp4'
import planeGif from '../../../examples/plane_flight.gif'
import planeMp4 from '../../../examples/plane_flight.mp4'

export interface Example {
  title: string
  prompt: string
  scenes: number
  length: string
  poster: string
  video: string
}

export const EXAMPLES: Example[] = [
  {
    title: 'How wings create lift',
    prompt: 'How do planes fly?',
    scenes: 5,
    length: '1:36',
    poster: planeGif,
    video: planeMp4,
  },
  {
    title: "Einstein's famous equation",
    prompt: 'Explain E = mc² to a curious teenager',
    scenes: 4,
    length: '1:39',
    poster: einsteinGif,
    video: einsteinMp4,
  },
  {
    title: 'How photosynthesis works',
    prompt: 'How photosynthesis works',
    scenes: 5,
    length: '1:50',
    poster: photosynthesisGif,
    video: photosynthesisMp4,
  },
  {
    title: 'How bees make honey',
    prompt: 'How do bees make honey?',
    scenes: 4,
    length: '1:41',
    poster: beesGif,
    video: beesMp4,
  },
]

export const PROMPT_IDEAS = [
  'Why is the sky blue?',
  'How does a vaccine train your immune system?',
  'What is compound interest?',
  'How do noise-cancelling headphones work?',
  'Why did the Roman Empire fall?',
  'How do bees make honey?',
  'What happens inside a black hole?',
  'How does GPS know where you are?',
  'How the printing press changed the world',
  'Why do we dream?',
  'What is inflation, simply explained?',
  'How do volcanoes erupt?',
]
