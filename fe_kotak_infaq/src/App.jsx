import Header from "./components/Header";
import StatusCard from "./components/StatusCard";
import VideoPanel from "./components/VideoPanel";
import CameraSection from "./components/cameraSection";

export default function App() {
  return (
    <div className="min-h-screen bg-emerald-600">
      <Header />
      {/* <StatusCard /> */}
      {/* <VideoPanel /> */}
      <CameraSection />
    </div>
  );
}
