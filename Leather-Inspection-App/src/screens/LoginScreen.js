import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  Animated, KeyboardAvoidingView, Platform, Dimensions,
} from 'react-native';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

const C = {
  bg: '#0d1117', card: '#161b22', border: '#30363d',
  text: '#e6edf3', dim: '#8b949e', muted: '#484f58',
  accent: '#f0883e', good: '#3fb950', bad: '#f85149', blue: '#58a6ff',
};

const VALID_USERS = [
  { username: 'admin', password: 'admin123', role: 'Supervisor' },
  { username: 'operator', password: 'operator123', role: 'Operator' },
  { username: 'team10', password: 'hidespec', role: 'Developer' },
];

// Animated particle component
function FloatingParticle({ delay, startX, startY, size, color, duration }) {
  const translateY = useRef(new Animated.Value(0)).current;
  const translateX = useRef(new Animated.Value(0)).current;
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const animate = () => {
      translateY.setValue(0);
      translateX.setValue(0);
      opacity.setValue(0);
      scale.setValue(0);

      Animated.sequence([
        Animated.delay(delay),
        Animated.parallel([
          Animated.timing(opacity, { toValue: 0.6, duration: 600, useNativeDriver: true }),
          Animated.spring(scale, { toValue: 1, friction: 4, useNativeDriver: true }),
        ]),
        Animated.parallel([
          Animated.timing(translateY, {
            toValue: -SCREEN_H * 0.4,
            duration: duration,
            useNativeDriver: true,
          }),
          Animated.timing(translateX, {
            toValue: (Math.random() - 0.5) * 100,
            duration: duration,
            useNativeDriver: true,
          }),
          Animated.sequence([
            Animated.timing(opacity, { toValue: 0.8, duration: duration * 0.3, useNativeDriver: true }),
            Animated.timing(opacity, { toValue: 0, duration: duration * 0.7, useNativeDriver: true }),
          ]),
        ]),
      ]).start(() => animate());
    };
    animate();
  }, []);

  return (
    <Animated.View
      style={{
        position: 'absolute',
        left: startX,
        top: startY,
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        opacity,
        transform: [{ translateY }, { translateX }, { scale }],
      }}
    />
  );
}

// Animated ring component
function PulseRing({ delay, size }) {
  const scale = useRef(new Animated.Value(0.5)).current;
  const opacity = useRef(new Animated.Value(0.6)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.parallel([
          Animated.timing(scale, { toValue: 2.5, duration: 2000, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 0, duration: 2000, useNativeDriver: true }),
        ]),
        Animated.parallel([
          Animated.timing(scale, { toValue: 0.5, duration: 0, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 0.6, duration: 0, useNativeDriver: true }),
        ]),
      ])
    ).start();
  }, []);

  return (
    <Animated.View
      style={{
        position: 'absolute',
        width: size,
        height: size,
        borderRadius: size / 2,
        borderWidth: 2,
        borderColor: C.accent,
        opacity,
        transform: [{ scale }],
      }}
    />
  );
}

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [loginSuccess, setLoginSuccess] = useState(false);

  // Main animations
  const bgGlow = useRef(new Animated.Value(0)).current;
  const logoScale = useRef(new Animated.Value(0)).current;
  const logoRotate = useRef(new Animated.Value(0)).current;
  const logoPulse = useRef(new Animated.Value(1)).current;
  const titleOpacity = useRef(new Animated.Value(0)).current;
  const titleSlide = useRef(new Animated.Value(-50)).current;
  const titleScale = useRef(new Animated.Value(0.5)).current;
  const subtitleOpacity = useRef(new Animated.Value(0)).current;
  const subtitleSlide = useRef(new Animated.Value(20)).current;
  const formOpacity = useRef(new Animated.Value(0)).current;
  const formSlide = useRef(new Animated.Value(60)).current;
  const input1Slide = useRef(new Animated.Value(80)).current;
  const input2Slide = useRef(new Animated.Value(80)).current;
  const buttonOpacity = useRef(new Animated.Value(0)).current;
  const buttonScale = useRef(new Animated.Value(0.3)).current;
  const hintOpacity = useRef(new Animated.Value(0)).current;
  const footerOpacity = useRef(new Animated.Value(0)).current;
  const errorShake = useRef(new Animated.Value(0)).current;
  const successScale = useRef(new Animated.Value(1)).current;
  const successOpacity = useRef(new Animated.Value(0)).current;
  const successRotate = useRef(new Animated.Value(0)).current;
  const whiteFlash = useRef(new Animated.Value(0)).current;

  // Scanning line animation
  const scanLineY = useRef(new Animated.Value(-10)).current;

  // Letter animations for "HideSpec"
  const letterAnims = useRef(
    Array.from({ length: 8 }, () => ({
      opacity: new Animated.Value(0),
      translateY: new Animated.Value(30),
      scale: new Animated.Value(0),
    }))
  ).current;

  useEffect(() => {
    // Background glow pulse
    Animated.loop(
      Animated.sequence([
        Animated.timing(bgGlow, { toValue: 1, duration: 3000, useNativeDriver: true }),
        Animated.timing(bgGlow, { toValue: 0, duration: 3000, useNativeDriver: true }),
      ])
    ).start();

    // Scanning line
    Animated.loop(
      Animated.sequence([
        Animated.timing(scanLineY, { toValue: 80, duration: 1500, useNativeDriver: true }),
        Animated.timing(scanLineY, { toValue: -10, duration: 0, useNativeDriver: true }),
        Animated.delay(500),
      ])
    ).start();

    // Main entrance sequence
    Animated.sequence([
      // 1. Logo drops in with spin
      Animated.parallel([
        Animated.spring(logoScale, { toValue: 1, friction: 3, tension: 40, useNativeDriver: true }),
        Animated.timing(logoRotate, { toValue: 2, duration: 1200, useNativeDriver: true }),
      ]),

      // 2. Letters of "HideSpec" pop in one by one
      Animated.stagger(80, letterAnims.map(anim =>
        Animated.parallel([
          Animated.spring(anim.opacity, { toValue: 1, friction: 5, useNativeDriver: true }),
          Animated.spring(anim.translateY, { toValue: 0, friction: 4, tension: 50, useNativeDriver: true }),
          Animated.spring(anim.scale, { toValue: 1, friction: 3, tension: 60, useNativeDriver: true }),
        ])
      )),

      // 3. Subtitle slides in
      Animated.parallel([
        Animated.timing(subtitleOpacity, { toValue: 1, duration: 400, useNativeDriver: true }),
        Animated.spring(subtitleSlide, { toValue: 0, friction: 6, useNativeDriver: true }),
      ]),

      // 4. Form container fades in
      Animated.timing(formOpacity, { toValue: 1, duration: 300, useNativeDriver: true }),

      // 5. Input fields slide in one after another
      Animated.stagger(150, [
        Animated.spring(input1Slide, { toValue: 0, friction: 5, tension: 40, useNativeDriver: true }),
        Animated.spring(input2Slide, { toValue: 0, friction: 5, tension: 40, useNativeDriver: true }),
      ]),

      // 6. Button bounces in
      Animated.parallel([
        Animated.spring(buttonScale, { toValue: 1, friction: 3, tension: 50, useNativeDriver: true }),
        Animated.timing(buttonOpacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      ]),

      // 7. Hint fades in
      Animated.timing(hintOpacity, { toValue: 1, duration: 500, useNativeDriver: true }),

      // 8. Footer
      Animated.timing(footerOpacity, { toValue: 1, duration: 500, useNativeDriver: true }),
    ]).start();

    // Continuous logo pulse
    Animated.loop(
      Animated.sequence([
        Animated.timing(logoPulse, { toValue: 1.08, duration: 1200, useNativeDriver: true }),
        Animated.timing(logoPulse, { toValue: 1, duration: 1200, useNativeDriver: true }),
      ])
    ).start();
  }, []);

  const shakeError = () => {
    Animated.sequence([
      Animated.timing(errorShake, { toValue: 15, duration: 40, useNativeDriver: true }),
      Animated.timing(errorShake, { toValue: -15, duration: 40, useNativeDriver: true }),
      Animated.timing(errorShake, { toValue: 12, duration: 40, useNativeDriver: true }),
      Animated.timing(errorShake, { toValue: -12, duration: 40, useNativeDriver: true }),
      Animated.timing(errorShake, { toValue: 8, duration: 40, useNativeDriver: true }),
      Animated.timing(errorShake, { toValue: -8, duration: 40, useNativeDriver: true }),
      Animated.timing(errorShake, { toValue: 0, duration: 40, useNativeDriver: true }),
    ]).start();
  };

  const handleLogin = () => {
    setError('');
    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password');
      shakeError();
      return;
    }

    setIsLoading(true);

    setTimeout(() => {
      const user = VALID_USERS.find(
        u => u.username.toLowerCase() === username.toLowerCase() && u.password === password
      );

      if (user) {
        setLoginSuccess(true);
        // Success animation sequence
        Animated.sequence([
          // Flash white
          Animated.timing(whiteFlash, { toValue: 0.3, duration: 150, useNativeDriver: true }),
          Animated.timing(whiteFlash, { toValue: 0, duration: 150, useNativeDriver: true }),
          // Checkmark appears with spin
          Animated.parallel([
            Animated.timing(successOpacity, { toValue: 1, duration: 300, useNativeDriver: true }),
            Animated.spring(successScale, { toValue: 1.2, friction: 3, useNativeDriver: true }),
            Animated.timing(successRotate, { toValue: 1, duration: 500, useNativeDriver: true }),
          ]),
          Animated.delay(400),
          // Everything flies out
          Animated.parallel([
            Animated.timing(formOpacity, { toValue: 0, duration: 400, useNativeDriver: true }),
            Animated.timing(formSlide, { toValue: -100, duration: 400, useNativeDriver: true }),
            Animated.spring(logoScale, { toValue: 2, friction: 5, useNativeDriver: true }),
            Animated.timing(subtitleOpacity, { toValue: 0, duration: 300, useNativeDriver: true }),
            Animated.timing(hintOpacity, { toValue: 0, duration: 200, useNativeDriver: true }),
            Animated.timing(footerOpacity, { toValue: 0, duration: 200, useNativeDriver: true }),
            ...letterAnims.map(a =>
              Animated.timing(a.opacity, { toValue: 0, duration: 300, useNativeDriver: true })
            ),
          ]),
          Animated.delay(200),
        ]).start(() => {
          onLogin(user);
        });
      } else {
        setIsLoading(false);
        setError('Invalid username or password');
        shakeError();
      }
    }, 1500);
  };

  const spin = logoRotate.interpolate({
    inputRange: [0, 2],
    outputRange: ['0deg', '720deg'],
  });

  const successSpin = successRotate.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  const glowOpacity = bgGlow.interpolate({
    inputRange: [0, 1],
    outputRange: [0.03, 0.08],
  });

  const letters = 'HideSpec'.split('');

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Animated background glow */}
      <Animated.View style={[styles.bgGlow, styles.bgGlow1, { opacity: glowOpacity }]} />
      <Animated.View style={[styles.bgGlow, styles.bgGlow2, { opacity: glowOpacity }]} />
      <Animated.View style={[styles.bgGlow, styles.bgGlow3, { opacity: glowOpacity }]} />

      {/* Floating particles */}
      <FloatingParticle delay={0} startX={50} startY={SCREEN_H * 0.7} size={6} color={C.accent} duration={4000} />
      <FloatingParticle delay={800} startX={SCREEN_W - 80} startY={SCREEN_H * 0.8} size={4} color={C.blue} duration={3500} />
      <FloatingParticle delay={1600} startX={SCREEN_W * 0.3} startY={SCREEN_H * 0.75} size={5} color={C.good} duration={4500} />
      <FloatingParticle delay={2400} startX={SCREEN_W * 0.7} startY={SCREEN_H * 0.65} size={3} color={C.accent} duration={3800} />
      <FloatingParticle delay={400} startX={SCREEN_W * 0.5} startY={SCREEN_H * 0.85} size={7} color={C.blue} duration={5000} />
      <FloatingParticle delay={1200} startX={80} startY={SCREEN_H * 0.6} size={4} color={C.accent} duration={4200} />
      <FloatingParticle delay={2000} startX={SCREEN_W - 60} startY={SCREEN_H * 0.7} size={5} color={C.good} duration={3600} />
      <FloatingParticle delay={3000} startX={SCREEN_W * 0.4} startY={SCREEN_H * 0.9} size={6} color={C.accent} duration={4800} />

      {/* Logo with pulse rings */}
      <View style={styles.logoArea}>
        <PulseRing delay={0} size={110} />
        <PulseRing delay={700} size={110} />
        <PulseRing delay={1400} size={110} />

        <Animated.View style={{
          transform: [
            { scale: Animated.multiply(logoScale, logoPulse) },
            { rotate: spin },
          ],
        }}>
          <View style={styles.logoOuter}>
            <View style={styles.logoMiddle}>
              <View style={styles.logoInner}>
                {/* Leather hide shape */}
                <View style={styles.hideShape}>
                  <View style={styles.hideBody} />
                  <View style={styles.hideTopLeft} />
                  <View style={styles.hideTopRight} />
                  <View style={styles.hideBottomLeft} />
                  <View style={styles.hideBottomRight} />
                </View>
                {/* Defect marks on the hide */}
                <View style={[styles.defectMark, { top: 16, left: 20 }]} />
                <View style={[styles.defectMark, styles.defectMarkRed, { top: 28, left: 30 }]} />
                <View style={[styles.defectMark, styles.defectMarkBlue, { top: 20, left: 34 }]} />
                {/* Magnifying glass */}
                <View style={styles.magGlass}>
                  <View style={styles.magLens} />
                  <View style={styles.magHandle} />
                </View>
                {/* Scanning line */}
                <Animated.View style={[styles.scanLine, { transform: [{ translateY: scanLineY }] }]} />
              </View>
            </View>
          </View>
        </Animated.View>
      </View>

      {/* App name - letter by letter */}
      <View style={styles.titleRow}>
        {letters.map((letter, i) => (
          <Animated.Text
            key={`letter-${i}`}
            style={[
              styles.titleLetter,
              {
                opacity: letterAnims[i].opacity,
                transform: [
                  { translateY: letterAnims[i].translateY },
                  { scale: letterAnims[i].scale },
                ],
              },
            ]}
          >
            {letter}
          </Animated.Text>
        ))}
      </View>

      {/* Subtitle */}
      <Animated.View style={{
        opacity: subtitleOpacity,
        transform: [{ translateY: subtitleSlide }],
      }}>
        <Text style={styles.subtitle}>Leather Hide Inspection System</Text>
        <View style={styles.dividerRow}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerDot}>◆</Text>
          <View style={styles.dividerLine} />
        </View>
        <Text style={styles.teamText}>TEAM 10 · TIP QUEZON CITY</Text>
      </Animated.View>

      {/* Form */}
      <Animated.View style={[
        styles.formContainer,
        {
          opacity: formOpacity,
          transform: [{ translateY: formSlide }, { translateX: errorShake }],
        },
      ]}>
        {/* Username input */}
        <Animated.View style={[styles.inputWrap, { transform: [{ translateX: input1Slide }] }]}>
          <View style={styles.inputContainer}>
            <View style={styles.inputIconBox}>
              <Text style={styles.inputIcon}>◉</Text>
            </View>
            <TextInput
              style={styles.input}
              placeholder="Username"
              placeholderTextColor={C.muted}
              value={username}
              onChangeText={(t) => { setUsername(t); setError(''); }}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
        </Animated.View>

        {/* Password input */}
        <Animated.View style={[styles.inputWrap, { transform: [{ translateX: input2Slide }] }]}>
          <View style={styles.inputContainer}>
            <View style={styles.inputIconBox}>
              <Text style={styles.inputIcon}>◆</Text>
            </View>
            <TextInput
              style={styles.input}
              placeholder="Password"
              placeholderTextColor={C.muted}
              value={password}
              onChangeText={(t) => { setPassword(t); setError(''); }}
              secureTextEntry={!showPassword}
              autoCapitalize="none"
            />
            <TouchableOpacity onPress={() => setShowPassword(!showPassword)} style={styles.eyeBtn}>
              <Text style={styles.eyeText}>{showPassword ? '◉' : '◎'}</Text>
            </TouchableOpacity>
          </View>
        </Animated.View>

        {/* Error */}
        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>⚠ {error}</Text>
          </View>
        ) : null}

        {/* Success checkmark overlay */}
        {loginSuccess && (
          <Animated.View style={[styles.successOverlay, {
            opacity: successOpacity,
            transform: [{ scale: successScale }, { rotate: successSpin }],
          }]}>
            <View style={styles.successCircle}>
              <Text style={styles.successCheck}>✓</Text>
            </View>
          </Animated.View>
        )}

        {/* Login button */}
        <Animated.View style={{ opacity: buttonOpacity, transform: [{ scale: buttonScale }] }}>
          <TouchableOpacity
            style={[styles.loginBtn, isLoading && styles.loginBtnLoading]}
            onPress={handleLogin}
            disabled={isLoading}
            activeOpacity={0.7}
          >
            {isLoading ? (
              <View style={styles.loadingRow}>
                <LoadingDot delay={0} />
                <LoadingDot delay={200} />
                <LoadingDot delay={400} />
              </View>
            ) : (
              <>
                <Text style={styles.loginBtnText}>SIGN IN</Text>
                <Text style={styles.loginArrow}>→</Text>
              </>
            )}
          </TouchableOpacity>
        </Animated.View>

        {/* Hint */}
        <Animated.View style={[styles.hintBox, { opacity: hintOpacity }]}>
          <Text style={styles.hintTitle}>DEMO ACCOUNTS</Text>
          <View style={styles.hintRow}>
            <Text style={styles.hintLabel}>Supervisor</Text>
            <Text style={styles.hintCred}>admin / admin123</Text>
          </View>
          <View style={styles.hintRow}>
            <Text style={styles.hintLabel}>Operator</Text>
            <Text style={styles.hintCred}>operator / operator123</Text>
          </View>
          <View style={styles.hintRow}>
            <Text style={styles.hintLabel}>Developer</Text>
            <Text style={styles.hintCred}>team10 / hidespec</Text>
          </View>
        </Animated.View>
      </Animated.View>

      {/* Footer */}
      <Animated.View style={[styles.footer, { opacity: footerOpacity }]}>
        <Text style={styles.footerText}>CPE 026 · EMERGING TECHNOLOGY 3</Text>
      </Animated.View>

      {/* White flash on success */}
      <Animated.View style={[styles.flash, { opacity: whiteFlash }]} pointerEvents="none" />
    </KeyboardAvoidingView>
  );
}

// Bouncing loading dot
function LoadingDot({ delay }) {
  const bounce = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(bounce, { toValue: -12, duration: 300, useNativeDriver: true }),
        Animated.timing(bounce, { toValue: 0, duration: 300, useNativeDriver: true }),
        Animated.delay(600 - delay),
      ])
    ).start();
  }, []);

  return (
    <Animated.View style={[styles.dot, { transform: [{ translateY: bounce }] }]} />
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1, backgroundColor: C.bg, alignItems: 'center',
    justifyContent: 'center', paddingHorizontal: 32,
  },

  // Background glows
  bgGlow: { position: 'absolute', borderRadius: 999 },
  bgGlow1: {
    width: 300, height: 300, top: -50, left: -100,
    backgroundColor: C.accent,
  },
  bgGlow2: {
    width: 250, height: 250, bottom: 100, right: -80,
    backgroundColor: C.blue,
  },
  bgGlow3: {
    width: 200, height: 200, top: SCREEN_H * 0.4, left: SCREEN_W * 0.3,
    backgroundColor: C.good,
  },

  // Logo
  logoArea: {
    width: 120, height: 120, justifyContent: 'center', alignItems: 'center',
    marginBottom: 16,
  },
  logoOuter: {
    width: 96, height: 96, borderRadius: 48,
    backgroundColor: 'rgba(240,136,62,0.08)',
    borderWidth: 2, borderColor: 'rgba(240,136,62,0.25)',
    justifyContent: 'center', alignItems: 'center',
  },
  logoMiddle: {
    width: 76, height: 76, borderRadius: 38,
    backgroundColor: 'rgba(240,136,62,0.12)',
    borderWidth: 1, borderColor: 'rgba(240,136,62,0.3)',
    justifyContent: 'center', alignItems: 'center',
  },
  logoInner: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: 'rgba(240,136,62,0.18)',
    justifyContent: 'center', alignItems: 'center',
    overflow: 'hidden',
  },
  // Leather hide shape (irregular organic shape using overlapping rounded views)
  hideShape: {
    position: 'absolute', width: 30, height: 26,
    top: 12, left: 10,
  },
  hideBody: {
    position: 'absolute', width: 26, height: 20,
    backgroundColor: 'rgba(180,130,80,0.7)',
    borderRadius: 8, top: 3, left: 2,
    transform: [{ rotate: '-5deg' }],
  },
  hideTopLeft: {
    position: 'absolute', width: 8, height: 8,
    backgroundColor: 'rgba(180,130,80,0.5)',
    borderRadius: 4, top: 0, left: 0,
  },
  hideTopRight: {
    position: 'absolute', width: 7, height: 7,
    backgroundColor: 'rgba(180,130,80,0.5)',
    borderRadius: 3.5, top: 0, right: 2,
  },
  hideBottomLeft: {
    position: 'absolute', width: 7, height: 7,
    backgroundColor: 'rgba(180,130,80,0.5)',
    borderRadius: 3.5, bottom: 0, left: 1,
  },
  hideBottomRight: {
    position: 'absolute', width: 8, height: 8,
    backgroundColor: 'rgba(180,130,80,0.5)',
    borderRadius: 4, bottom: 0, right: 0,
  },
  // Defect marks on the hide
  defectMark: {
    position: 'absolute', width: 4, height: 4,
    borderRadius: 2, backgroundColor: C.accent,
  },
  defectMarkRed: { backgroundColor: C.bad, width: 3, height: 3, borderRadius: 1.5 },
  defectMarkBlue: { backgroundColor: C.blue, width: 3, height: 3, borderRadius: 1.5 },
  // Magnifying glass
  magGlass: {
    position: 'absolute', bottom: 6, right: 6,
  },
  magLens: {
    width: 18, height: 18, borderRadius: 9,
    borderWidth: 2.5, borderColor: C.accent,
    backgroundColor: 'rgba(240,136,62,0.08)',
  },
  magHandle: {
    position: 'absolute', bottom: -5, right: -5,
    width: 8, height: 2.5,
    backgroundColor: C.accent, borderRadius: 1,
    transform: [{ rotate: '45deg' }],
  },
  scanLine: {
    position: 'absolute', left: 4, right: 4,
    height: 2, backgroundColor: C.accent, opacity: 0.5,
    borderRadius: 1,
  },

  // Title letters
  titleRow: {
    flexDirection: 'row', justifyContent: 'center', marginBottom: 8,
  },
  titleLetter: {
    fontSize: 38, fontWeight: '900', color: C.accent, letterSpacing: -1,
  },

  // Subtitle
  subtitle: {
    fontSize: 13, color: C.dim, textAlign: 'center', letterSpacing: 0.5,
  },
  dividerRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    marginVertical: 10, gap: 10,
  },
  dividerLine: { width: 40, height: 1, backgroundColor: C.border },
  dividerDot: { fontSize: 8, color: C.accent },
  teamText: {
    fontSize: 9, color: C.muted, textAlign: 'center',
    letterSpacing: 2, fontWeight: '700',
  },

  // Form
  formContainer: { width: '100%', marginTop: 24 },
  inputWrap: { marginBottom: 12 },
  inputContainer: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.card, borderRadius: 12,
    borderWidth: 1, borderColor: C.border,
    overflow: 'hidden',
  },
  inputIconBox: {
    width: 48, height: 52, justifyContent: 'center', alignItems: 'center',
    backgroundColor: 'rgba(240,136,62,0.06)',
    borderRightWidth: 1, borderRightColor: C.border,
  },
  inputIcon: { fontSize: 16, color: C.accent },
  input: {
    flex: 1, height: 52, color: C.text, fontSize: 14, paddingHorizontal: 14,
  },
  eyeBtn: { padding: 14 },
  eyeText: { fontSize: 18, color: C.muted },

  // Error
  errorBox: {
    backgroundColor: 'rgba(248,81,73,0.1)', borderRadius: 10,
    padding: 12, marginBottom: 12,
    borderWidth: 1, borderColor: 'rgba(248,81,73,0.25)',
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
  },
  errorText: { color: C.bad, fontSize: 12, fontWeight: '700' },

  // Success
  successOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    justifyContent: 'center', alignItems: 'center', zIndex: 10,
  },
  successCircle: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: 'rgba(63,185,80,0.15)',
    borderWidth: 3, borderColor: C.good,
    justifyContent: 'center', alignItems: 'center',
  },
  successCheck: { fontSize: 36, color: C.good, fontWeight: '900' },

  // Button
  loginBtn: {
    backgroundColor: C.accent, borderRadius: 12,
    height: 54, flexDirection: 'row',
    justifyContent: 'center', alignItems: 'center', gap: 8,
  },
  loginBtnLoading: { backgroundColor: 'rgba(240,136,62,0.6)' },
  loginBtnText: {
    color: '#fff', fontSize: 15, fontWeight: '900', letterSpacing: 3,
  },
  loginArrow: { color: '#fff', fontSize: 18, fontWeight: '300' },
  loadingRow: { flexDirection: 'row', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#fff' },

  // Hint
  hintBox: {
    marginTop: 20, padding: 14,
    backgroundColor: 'rgba(88,166,255,0.05)', borderRadius: 12,
    borderWidth: 1, borderColor: 'rgba(88,166,255,0.12)',
  },
  hintTitle: {
    fontSize: 9, fontWeight: '800', color: C.blue,
    letterSpacing: 2, marginBottom: 10, textAlign: 'center',
  },
  hintRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: 4, borderBottomWidth: 1,
    borderBottomColor: 'rgba(88,166,255,0.06)',
  },
  hintLabel: { fontSize: 11, color: C.dim, fontWeight: '600' },
  hintCred: { fontSize: 11, color: C.muted, fontFamily: 'monospace' },

  // Footer
  footer: { position: 'absolute', bottom: 30 },
  footerText: { fontSize: 9, color: C.muted, letterSpacing: 2, fontWeight: '600' },

  // Flash
  flash: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: '#fff',
  },
});