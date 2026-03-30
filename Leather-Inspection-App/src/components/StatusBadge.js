import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export default function StatusBadge({ classification, size = 'medium' }) {
  const isGood = classification === 'Good';
  const sizes = {
    small: { paddingH: 10, paddingV: 4, fontSize: 10, dotSize: 6 },
    medium: { paddingH: 14, paddingV: 6, fontSize: 12, dotSize: 7 },
    large: { paddingH: 18, paddingV: 8, fontSize: 14, dotSize: 8 },
  };
  const s = sizes[size] || sizes.medium;

  return (
    <View
      style={[
        styles.badge,
        {
          backgroundColor: isGood ? 'rgba(63,185,80,0.12)' : 'rgba(248,81,73,0.12)',
          borderColor: isGood ? 'rgba(63,185,80,0.3)' : 'rgba(248,81,73,0.3)',
          paddingHorizontal: s.paddingH,
          paddingVertical: s.paddingV,
        },
      ]}
    >
      <View
        style={[
          styles.dot,
          {
            width: s.dotSize,
            height: s.dotSize,
            borderRadius: s.dotSize / 2,
            backgroundColor: isGood ? '#3fb950' : '#f85149',
          },
        ]}
      />
      <Text
        style={[
          styles.text,
          {
            color: isGood ? '#3fb950' : '#f85149',
            fontSize: s.fontSize,
          },
        ]}
      >
        {isGood ? 'PASSED' : 'FAILED'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderRadius: 6,
    borderWidth: 1,
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
  },
  dot: {
    marginRight: 6,
  },
  text: {
    fontWeight: '800',
    letterSpacing: 1.2,
  },
});