import { Component, type ReactNode } from 'react'
import { reportProblem } from '../report'

// If a screen crashes while drawing, React would show a blank page. This
// shows a plain message and a way back instead, and sends the details to
// app.log (with a reference code the person can quote).
export default class CrashScreen extends Component<{ children: ReactNode }, { crashed: boolean; ref: string | null }> {
  state = { crashed: false, ref: null as string | null }

  static getDerivedStateFromError() {
    return { crashed: true }
  }

  componentDidCatch(error: unknown) {
    reportProblem('screen crashed', error).then((ref) => this.setState({ ref }))
  }

  render() {
    if (!this.state.crashed) return this.props.children
    return (
      <div className="page crash-screen" role="alert">
        <h1 className="settings-title">Something went wrong</h1>
        <p className="set-note">
          OnTrack ran into a problem showing this screen. Your list is safe on the server.
          {this.state.ref && <> (ref {this.state.ref})</>}
        </p>
        <button className="btn btn-primary" onClick={() => window.location.assign('/')}>Reload OnTrack</button>
      </div>
    )
  }
}
