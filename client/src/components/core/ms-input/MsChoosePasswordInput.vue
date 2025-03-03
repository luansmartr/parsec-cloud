<!-- Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 2016-present Scille SAS -->

<template>
  <div class="info-password">
    <img
      src="@/assets/images/password.svg"
      alt="password-image"
      class="info-password__img"
    >
    <ion-text
      class="subtitles-sm info-password__text"
    >
      {{ $t('Password.passwordInfo') }}
    </ion-text>
  </div>
  <div class="ms-password-inputs">
    <div class="ms-password-inputs-container">
      <ms-password-input
        :label="$t('Password.password')"
        v-model="password"
        name="password"
        @change="onPasswordChange()"
        @on-enter-keyup="$emit('onEnterKeyup', password)"
      />
    </div>
    <div class="ms-password-inputs-container">
      <ms-password-input
        :label="$t('Password.confirmPassword')"
        v-model="passwordConfirm"
        name="confirmPassword"
        @on-enter-keyup="$emit('onEnterKeyup', passwordConfirm)"
      />
      <span
        class="form-helperText"
        v-if="password !== passwordConfirm"
      >
        {{ $t('Password.noMatch') }}
      </span>
    </div>
  </div>
  <div class="password-level-container">
    <div
      class="password-level"
      :class="getPasswordLevelClass()"
    >
      <div class="password-level-bar">
        <div class="bar-item" />
        <div class="bar-item" />
        <div class="bar-item" />
      </div>
      <ion-text
        class="subtitles-sm password-level__text"
      >
        {{ getPasswordStrengthText($t, passwordStrength) }}
      </ion-text>
    </div>
    <ion-text
      class="subtitles-sm password-criteria"
    >
      {{ $t('Password.passwordCriteria') }}
    </ion-text>
  </div>
</template>

<script setup lang="ts">
import { IonText } from '@ionic/vue';
import { ref } from 'vue';
import MsPasswordInput from '@/components/core/ms-input/MsPasswordInput.vue';
import { PasswordStrength, getPasswordStrength, getPasswordStrengthText } from '@/common/passwordValidation';

const password = ref('');
const passwordConfirm = ref('');
const passwordStrength = ref(PasswordStrength.None);

defineEmits<{
  (e: 'onEnterKeyup', value: string): void
}>();

defineExpose({
  areFieldsCorrect,
  password,
});

async function areFieldsCorrect(): Promise<boolean> {
  return passwordStrength.value === PasswordStrength.High && password.value === passwordConfirm.value;
}

function onPasswordChange(): void {
  passwordStrength.value = getPasswordStrength(password.value);
}

function getPasswordLevelClass() : string {
  if (passwordStrength.value === PasswordStrength.Low) {
    return 'password-level-low';
  } else if (passwordStrength.value === PasswordStrength.Medium) {
    return 'password-level-medium';
  } else if (passwordStrength.value === PasswordStrength.High) {
    return 'password-level-high';
  }
  return '';
}
</script>

<style scoped lang="scss">
.info-password {
  background: var(--parsec-color-light-primary-30);
  display: flex;
  align-items: center;
  gap: .625rem;
  width: 100%;
  padding: .625rem;
  border-radius: var(--parsec-radius-6);
  margin-bottom: .5rem;

  &__img {
    width: 3.25rem;
    height: 3.25rem;
    margin-right: .5rem;
  }

  &__text {
    color: var(--parsec-color-light-secondary-text);
  }
}

.ms-password-inputs {
  display: flex;
  gap: 1.5rem;

  &-container {
    width: 100%;
  }

  .form-helperText {
    display: flex;
    flex-direction: column;
    margin-top: .5rem;
    color: var(--parsec-color-light-danger-500);
  }
}

.password-level-container {
  display: flex;
  flex-direction: column;
  gap: .5rem;
  max-width: 35rem;

  .password-level {
  display: flex;
  flex-direction: column;
  gap: .5rem;

    &__text {
      color: var(--parsec-color-light-secondary-text);
    }

    &-bar {
      display: flex;
      gap: .5rem;

      .bar-item {
        width: 3rem;
        height: .375rem;
        border-radius: var(--parsec-radius-6);
        background: var(--parsec-color-light-primary-50);
        position: relative;
      }
    }

    &.password-level-low {
      .password-level__text {
        color: var(--parsec-color-light-danger-500);
      }

      .bar-item:nth-child(-n+1) {
        background: var(--parsec-color-light-danger-500);
      }
    }

    &.password-level-medium {
      .password-level__text {
        color: var(--parsec-color-light-warning-500);
      }

      .bar-item:nth-child(-n+2) {
        background: var(--parsec-color-light-warning-500);
      }
    }

    &.password-level-high {
      .password-level__text {
        color: var(--parsec-color-light-success-500);
      }

      .bar-item:nth-child(-n+3) {
        background: var(--parsec-color-light-success-500);
      }
    }
  }

  .password-criteria {
    color: var(--parsec-color-light-secondary-grey);
  }
}
</style>
