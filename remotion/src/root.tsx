import React from 'react';
import {Composition} from 'remotion';
import {ColorsLesson} from './colors';

export const Root: React.FC = () => (
  <Composition
    id="ColorsLesson"
    component={ColorsLesson}
    durationInFrames={300}
    fps={30}
    width={1280}
    height={720}
    defaultProps={{colorName: 'أحمر', colorHex: '#e53935'}}
  />
);
