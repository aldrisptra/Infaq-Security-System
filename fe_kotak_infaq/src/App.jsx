import Header from "./components/Header";
import StatusCard from "./components/StatusCard";
import VideoPanel from "./components/VideoPanel";
import CameraSection from "./components/CameraSection";

export default function App() {
  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 py-8">
        <CameraSection />
      </main>
    </div>
  );
}
