import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

const defaultTheme = {
  good: '#3fb950',
  bad: '#f85149',
  goodSoft: 'rgba(63,185,80,0.12)',
  badSoft: 'rgba(248,81,73,0.12)',
  goodSoftBorder: 'rgba(63,185,80,0.3)',
  badSoftBorder: 'rgba(248,81,73,0.3)',
};

export default function StatusBadge({ classification, size = 'medium', theme }) {
  const C = theme || defaultTheme;
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
          backgroundColor: isGood ? C.goodSoft : C.badSoft,
          borderColor: isGood ? C.goodSoftBorder : C.badSoftBorder,
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
            backgroundColor: isGood ? C.good : C.bad,
          },
        ]}
      />
      <Text
        style={[
          styles.text,
          {
            color: isGood ? C.good : C.bad,
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