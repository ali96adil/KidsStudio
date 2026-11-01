import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';

export const ColorsLesson: React.FC<{colorName: string; colorHex: string}> = ({colorName, colorHex}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, 20, 260, 290], [0.75, 1, 1, 0.85], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill style={{backgroundColor: '#fff9ed', alignItems: 'center', justifyContent: 'center', fontFamily: 'sans-serif'}}>
      <div style={{fontSize: 68, fontWeight: 700, color: '#292929', marginBottom: 32, direction: 'rtl'}}>هيا نتعلم الألوان</div>
      <div style={{width: 280, height: 280, borderRadius: '50%', backgroundColor: colorHex, transform: `scale(${scale})`}} />
      <div style={{fontSize: 90, fontWeight: 800, color: '#292929', marginTop: 32}}>{colorName}</div>
    </AbsoluteFill>
  );
};
