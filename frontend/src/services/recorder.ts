/** Encode Float32 mono PCM samples into a WAV ArrayBuffer (16-bit PCM). */
export function encodeWavMono(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const numFrames = samples.length
  const bytesPerSample = 2
  const blockAlign = bytesPerSample
  const buffer = new ArrayBuffer(44 + numFrames * bytesPerSample)
  const view = new DataView(buffer)

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + numFrames * bytesPerSample, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, numFrames * bytesPerSample, true)

  let offset = 44
  for (let i = 0; i < numFrames; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }
  return buffer
}

export type RecorderHandle = {
  stop: () => Promise<Blob>
  elapsedMs: () => number
}

/**
 * Record microphone audio as a mono WAV blob (no MediaRecorder/ffmpeg needed).
 */
export async function startWavRecording(): Promise<RecorderHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  })
  const audioContext = new AudioContext()
  const source = audioContext.createMediaStreamSource(stream)
  const processor = audioContext.createScriptProcessor(4096, 1, 1)
  const chunks: Float32Array[] = []
  const started = performance.now()

  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0)
    chunks.push(new Float32Array(input))
  }

  source.connect(processor)
  processor.connect(audioContext.destination)

  return {
    elapsedMs: () => performance.now() - started,
    stop: async () => {
      processor.disconnect()
      source.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      const sampleRate = audioContext.sampleRate
      await audioContext.close()

      let total = 0
      for (const c of chunks) total += c.length
      const merged = new Float32Array(total)
      let offset = 0
      for (const c of chunks) {
        merged.set(c, offset)
        offset += c.length
      }
      const wav = encodeWavMono(merged, sampleRate)
      return new Blob([wav], { type: 'audio/wav' })
    },
  }
}
