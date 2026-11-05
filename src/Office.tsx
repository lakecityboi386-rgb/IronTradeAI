import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, ContactShadows, RoundedBox } from "@react-three/drei";
import * as THREE from "three";
export const names = [
  "Market Scout",
  "Technical Analyst",
  "Wallet Tracker",
  "Liquidity Analyst",
  "Risk Officer",
  "Execution Specialist",
  "Momentum Maverick",
  "Mean Reversion Quant",
];
export const colors = [
  "#45c9bf",
  "#7e9dff",
  "#bc95f6",
  "#67b9dc",
  "#d5b36e",
  "#de9975",
  "#92c97d",
  "#e493ad",
];
function Box({
  p,
  s,
  c = "#172633",
  metal = 0,
}: {
  p: [number, number, number];
  s: [number, number, number];
  c?: string;
  metal?: number;
}) {
  return (
    <mesh position={p} castShadow receiveShadow>
      <boxGeometry args={s} />
      <meshStandardMaterial color={c} metalness={metal} roughness={0.35} />
    </mesh>
  );
}
function Person({
  index,
  selected,
  onSelect,
}: {
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const arm = useRef<THREE.Group>(null),
    head = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (arm.current) arm.current.rotation.x = Math.sin(t * 4 + index) * 0.09;
    if (head.current)
      head.current.rotation.y = Math.sin(t * 0.55 + index) * 0.16;
  });
  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
    >
      <mesh position={[0, 0.79, 0.13]} castShadow>
        <capsuleGeometry args={[0.19, 0.37, 6, 12]} />
        <meshStandardMaterial color={selected ? colors[index] : "#263546"} />
      </mesh>
      <group ref={head} position={[0, 1.25, 0.12]}>
        <mesh castShadow>
          <sphereGeometry args={[0.145, 16, 16]} />
          <meshStandardMaterial
            color={["#b87958", "#d1a181", "#684633", "#b18a69"][index % 4]}
          />
        </mesh>
        <mesh position={[0, 0.065, -0.015]}>
          <sphereGeometry args={[0.143, 16, 16, 0, Math.PI * 2, 0, 1.55]} />
          <meshStandardMaterial color="#171d22" />
        </mesh>
      </group>
      {[-1, 1].map((sign) => (
        <group key={sign}>
          <Box
            p={[sign * 0.12, 0.47, -0.05]}
            s={[0.14, 0.16, 0.43]}
            c="#1b2330"
          />
          <Box
            p={[sign * 0.12, 0.27, -0.23]}
            s={[0.13, 0.4, 0.14]}
            c="#1b2330"
          />
          <Box
            p={[sign * 0.12, 0.07, -0.3]}
            s={[0.15, 0.1, 0.29]}
            c="#101218"
          />
        </group>
      ))}
      <group ref={arm} position={[0, 0.96, 0.02]}>
        {[-1, 1].map((sign) => (
          <group key={sign}>
            <mesh
              position={[sign * 0.25, -0.12, -0.03]}
              rotation={[0.3, 0, sign * 0.2]}
              castShadow
            >
              <capsuleGeometry args={[0.065, 0.24, 4, 8]} />
              <meshStandardMaterial color="#263546" />
            </mesh>
            <mesh
              position={[sign * 0.24, -0.26, -0.2]}
              rotation={[1.25, 0, 0]}
              castShadow
            >
              <capsuleGeometry args={[0.055, 0.24, 4, 8]} />
              <meshStandardMaterial color="#263546" />
            </mesh>
            <mesh position={[sign * 0.24, -0.23, -0.36]}>
              <sphereGeometry args={[0.065, 10, 10]} />
              <meshStandardMaterial color="#bc8b6d" />
            </mesh>
          </group>
        ))}
      </group>
    </group>
  );
}
function Desk({
  index,
  selected,
  onSelect,
}: {
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const x = ((index % 4) - 1.5) * 2.65,
    z = index < 4 ? -1.7 : 1.8;
  return (
    <group position={[x, 0, z]}>
      <RoundedBox
        position={[0, 0.81, -0.7]}
        args={[2.25, 0.1, 1.08]}
        radius={0.045}
        castShadow
        receiveShadow
        onClick={onSelect}
      >
        <meshStandardMaterial
          color="#2b3037"
          metalness={0.35}
          roughness={0.25}
        />
      </RoundedBox>
      {[-0.88, 0.88].map((a) => (
        <Box
          key={a}
          p={[a, 0.4, -0.7]}
          s={[0.07, 0.8, 0.76]}
          c="#111c25"
          metal={0.6}
        />
      ))}
      {[-0.48, 0.48].map((a, k) => (
        <group key={a} position={[a, 1.22, -0.94]} rotation={[0, a * 0.18, 0]}>
          <Box p={[0, 0, 0]} s={[0.87, 0.51, 0.045]} c="#080e14" />
          <Box p={[0, -0.32, 0]} s={[0.045, 0.18, 0.04]} c="#7b858b" />
          <Box p={[0, -0.4, 0]} s={[0.3, 0.025, 0.15]} />
          <mesh position={[0, 0, 0.026]}>
            <planeGeometry args={[0.79, 0.43]} />
            <meshBasicMaterial color="#0a1a28" />
          </mesh>
          {Array.from({ length: 12 }, (_, j) => (
            <mesh
              key={j}
              position={[
                -0.34 + j * 0.059,
                Math.sin(j * 1.6 + index + k) * 0.075 - 0.02,
                0.029,
              ]}
            >
              <planeGeometry
                args={[0.025, 0.035 + ((j * 7 + index * 3) % 9) * 0.014]}
              />
              <meshBasicMaterial
                color={j % 3 === 0 ? "#db9d73" : colors[index]}
              />
            </mesh>
          ))}
        </group>
      ))}
      <Box p={[0, 0.88, -0.47]} s={[0.55, 0.025, 0.18]} c="#090f16" />
      <Box p={[0, 0.5, 0.18]} s={[0.5, 0.09, 0.47]} c="#101921" />
      <Box p={[0, 0.83, 0.43]} s={[0.5, 0.6, 0.08]} c="#19242e" />
      <Box p={[0, 0.24, 0.18]} s={[0.07, 0.45, 0.07]} c="#77818a" metal={0.8} />
      <Person index={index} selected={selected} onSelect={onSelect} />
      {selected && (
        <pointLight
          position={[0, 1, 0.2]}
          color={colors[index]}
          intensity={3}
          distance={3}
        />
      )}
    </group>
  );
}
function World({
  selected,
  onSelect,
  boss,
}: {
  selected: number;
  onSelect: (i: number) => void;
  boss: boolean;
}) {
  return (
    <>
      <color attach="background" args={["#0a111b"]} />
      <fog attach="fog" args={["#101b2d", 22, 65]} />
      <ambientLight intensity={1.0} />
      <hemisphereLight args={["#a4c9ff", "#172335", 1.4]} />
      <directionalLight
        position={[6, 13, 5]}
        intensity={3.0}
        color="#e4d2af"
        castShadow
        shadow-mapSize={[2048, 2048]}
      />
      <Box p={[0, -0.15, 0]} s={[15, 0.25, 12]} c="#17232e" metal={0.4} />
      {Array.from({ length: 15 }, (_, i) => (
        <Box
          key={i}
          p={[-7 + i, 0.001, 0]}
          s={[0.012, 0.005, 12]}
          c="#32414d"
        />
      ))}
      <Box p={[0, 0.25, -5.3]} s={[15, 0.5, 0.16]} c="#101b28" />
      <Box p={[0, 4.4, -5.3]} s={[15, 0.2, 0.16]} c="#101b28" />
      {[-6, -3, 0, 3, 6].map((x) => (
        <group key={x}>
          <mesh position={[x, 2.4, -5.17]}>
            <boxGeometry args={[2.82, 3.8, 0.03]} />
            <meshPhysicalMaterial
              color="#6d9bb8"
              transparent
              opacity={0.13}
              roughness={0.15}
              metalness={0.1}
              depthWrite={false}
            />
          </mesh>
          <Box
            p={[x - 1.44, 2.4, -5.1]}
            s={[0.06, 4.1, 0.1]}
            c="#93816a"
            metal={0.8}
          />
        </group>
      ))}
      <Box p={[0, 1.5, -5.04]} s={[15, 0.06, 0.1]} c="#64717a" />
      {Array.from({ length: 36 }, (_, i) => {
        const h = 1.6 + ((i * 13) % 11) * 0.4;
        return (
          <group key={i} position={[-16 + i * 0.9, 0, -8 - (i % 3) * 1.7]}>
            <Box
              p={[0, h / 2, 0]}
              s={[0.65, h, 0.8]}
              c={i % 2 ? "#172a40" : "#21374b"}
            />
            {Array.from({ length: 6 }, (_, j) => (
              <Box
                key={j}
                p={[0.1, j * 0.5 + 0.3, 0.412]}
                s={[0.3, 0.045, 0.01]}
                c={j % 3 ? "#baa16a" : "#447b9f"}
              />
            ))}
          </group>
        );
      })}
      {[0, 1].map((i) => (
        <group key={i} position={[0, 0, i * 3.5 - 1.9]}>
          <Box p={[0, 3.3, -0.7]} s={[11, 0.055, 0.18]} c="#b3a484" />
          <pointLight
            position={[0, 3, -0.7]}
            intensity={22}
            distance={10}
            color="#b4d5ff"
          />
        </group>
      ))}
      <Box p={[6.25, 1.5, 1.4]} s={[0.04, 3, 7]} c="#284151" metal={0.85} />
      <Box p={[5.8, 0.85, 3.3]} s={[1.1, 0.12, 2]} c="#8a6f46" />
      <Box p={[-6.5, 0.3, 3.8]} s={[0.6, 0.6, 0.6]} c="#313239" />
      <mesh position={[-6.5, 1.1, 3.8]}>
        <sphereGeometry args={[0.55, 10, 10]} />
        <meshStandardMaterial color="#31574b" />
      </mesh>
      {names.map((_, i) => (
        <Desk
          key={i}
          index={i}
          selected={i === selected}
          onSelect={() => onSelect(i)}
        />
      ))}
      <ContactShadows
        position={[0, 0.01, 0]}
        opacity={0.5}
        scale={24}
        blur={2}
        far={5}
      />
      <OrbitControls
        makeDefault
        target={boss ? [3, 0.9, 1] : [0, 0.7, -0.2]}
        minDistance={5}
        maxDistance={22}
        maxPolarAngle={Math.PI / 2.12}
        minPolarAngle={0.25}
      />
    </>
  );
}
export default function Office({
  selected,
  onSelect,
  boss = false,
}: {
  selected: number;
  onSelect: (i: number) => void;
  boss?: boolean;
}) {
  return (
    <Canvas shadows camera={{ position: [9, 7, 11], fov: 43 }} dpr={[1, 1.5]}>
      <World selected={selected} onSelect={onSelect} boss={boss} />
    </Canvas>
  );
}
