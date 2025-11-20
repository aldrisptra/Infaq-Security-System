import Header from "./components/header.jsx";
import CameraSection from "./components/CameraSection.jsx";

export default function App() {
  return (
    <div style={{ fontFamily: "system-ui, Arial, sans-serif", padding: 16 }}>
      <Header />
      <CameraSection />
    </div>
  );
}
