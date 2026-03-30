import React, { useState, useRef, useEffect } from 'react';
import { Text, StatusBar, View, Animated, TouchableOpacity } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import LoginScreen from './src/screens/LoginScreen';
import LiveMonitorScreen from './src/screens/LiveMonitorScreen';
import AnalyticsScreen from './src/screens/AnalyticsScreen';
import AboutScreen from './src/screens/AboutScreen';

const Tab = createBottomTabNavigator();

export const THEME = {
  bg: '#0d1117',
  card: '#161b22',
  border: '#30363d',
  text: '#e6edf3',
  textDim: '#8b949e',
  textMuted: '#484f58',
  accent: '#f0883e',
  good: '#3fb950',
  bad: '#f85149',
  blue: '#58a6ff',
  headerBg: '#010409',
  tabBg: '#010409',
};

function MainApp({ user, onLogout }) {
  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(30)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeIn, { toValue: 1, duration: 500, useNativeDriver: true }),
      Animated.spring(slideUp, { toValue: 0, friction: 6, useNativeDriver: true }),
    ]).start();
  }, []);

  return (
    <Animated.View style={{ flex: 1, opacity: fadeIn, transform: [{ translateY: slideUp }] }}>
      <NavigationContainer>
        <StatusBar barStyle="light-content" backgroundColor={THEME.headerBg} />
        <Tab.Navigator
          screenOptions={{
            headerStyle: {
              backgroundColor: THEME.headerBg,
              elevation: 0,
              shadowOpacity: 0,
              borderBottomWidth: 1,
              borderBottomColor: THEME.border,
            },
            headerTintColor: THEME.text,
            headerTitleStyle: {
              fontWeight: '800',
              fontSize: 14,
              letterSpacing: 0.3,
            },
            headerRight: () => (
              <TouchableOpacity
                onPress={onLogout}
                style={{
                  marginRight: 16,
                  backgroundColor: 'rgba(248,81,73,0.1)',
                  borderRadius: 6,
                  paddingHorizontal: 10,
                  paddingVertical: 5,
                  borderWidth: 1,
                  borderColor: 'rgba(248,81,73,0.2)',
                }}
              >
                <Text style={{ color: '#f85149', fontSize: 10, fontWeight: '800', letterSpacing: 1 }}>
                  LOGOUT
                </Text>
              </TouchableOpacity>
            ),
            tabBarActiveTintColor: THEME.accent,
            tabBarInactiveTintColor: THEME.textMuted,
            tabBarStyle: {
              backgroundColor: THEME.tabBg,
              borderTopWidth: 1,
              borderTopColor: THEME.border,
              height: 64,
              paddingBottom: 8,
              paddingTop: 6,
            },
            tabBarLabelStyle: {
              fontSize: 10,
              fontWeight: '700',
              letterSpacing: 0.8,
              textTransform: 'uppercase',
            },
          }}
        >
          <Tab.Screen
            name="LiveMonitor"
            component={LiveMonitorScreen}
            options={{
              title: 'Monitor',
              headerTitle: `◈  HIDESPEC — ${user.role.toUpperCase()}`,
              tabBarIcon: ({ color }) => (
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 20, color }}>◉</Text>
                </View>
              ),
            }}
          />
          <Tab.Screen
            name="Analytics"
            component={AnalyticsScreen}
            options={{
              title: 'Analytics',
              headerTitle: '◈  HIDESPEC — ANALYTICS',
              tabBarIcon: ({ color }) => (
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 20, color }}>▦</Text>
                </View>
              ),
            }}
          />
          <Tab.Screen
            name="About"
            component={AboutScreen}
            options={{
              title: 'About',
              headerTitle: '◈  HIDESPEC — ABOUT',
              tabBarIcon: ({ color }) => (
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 20, color }}>◈</Text>
                </View>
              ),
            }}
          />
        </Tab.Navigator>
      </NavigationContainer>
    </Animated.View>
  );
}

export default function App() {
  const [user, setUser] = useState(null);

  const handleLogin = (userData) => {
    setUser(userData);
  };

  const handleLogout = () => {
    setUser(null);
  };

  if (!user) {
    return (
      <>
        <StatusBar barStyle="light-content" backgroundColor="#0d1117" />
        <LoginScreen onLogin={handleLogin} />
      </>
    );
  }

  return <MainApp user={user} onLogout={handleLogout} />;
}