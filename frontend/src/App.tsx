export default function App() {
  return (
    <div className="page">
      <header className="header">
        <div>
          <div className="brand">OnTrack</div>
          <div className="eyebrow">Your wish list, on budget</div>
        </div>
      </header>

      <div className="columns">
        <aside className="side">{/* budget card and add-link box go here */}</aside>
        <main className="main">{/* tabs and item list go here */}</main>
      </div>
    </div>
  )
}